import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlmodel import Session, create_engine, select

from app.ingest import pipeline
from app.models import Question, QuestionAttempt, User


class IngestTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.seed = root / 'seed'
        self.seed.mkdir()
        self.engine = create_engine(f'sqlite:///{(root / "test.db").as_posix()}')
        self.addCleanup(self.engine.dispose)
        patcher = patch.object(pipeline, 'engine', self.engine)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_questions(self, *names):
        rows = [dict(subject='行测', module='资料分析', content=name,
                     options=json.dumps({'A': '甲', 'B': '乙'}), answer='A',
                     source=f'测试卷#{name}') for name in names]
        (self.seed / 'questions.json').write_text(json.dumps(rows), encoding='utf-8')

    def test_default_dates_allow_persisting_question_user_and_attempt(self):
        self.write_questions('甲题')
        self.assertEqual(pipeline.run(self.seed)['inserted'], 1)
        with Session(self.engine) as session:
            question = session.exec(select(Question)).one()
            user = User(username='local-test')
            session.add(user)
            session.flush()
            session.add(QuestionAttempt(question_id=question.id, user_id=user.id, chosen='A'))
            session.commit()
            attempt = session.exec(select(QuestionAttempt)).one()
            self.assertIsNotNone(attempt.created_at)
            self.assertEqual(attempt.chosen, 'A')

    def test_rebuild_keeps_attempt_linked_when_input_order_changes(self):
        self.write_questions('甲题', '乙题')
        pipeline.run(self.seed)
        with Session(self.engine) as session:
            question = session.exec(select(Question).where(Question.content == '甲题')).one()
            session.add(QuestionAttempt(question_id=question.id, chosen='B', is_correct=False))
            session.commit()

        self.write_questions('乙题', '甲题', '丙题')
        pipeline.run(self.seed, rebuild=True)

        with Session(self.engine) as session:
            attempt = session.exec(select(QuestionAttempt)).one()
            self.assertEqual(session.get(Question, attempt.question_id).content, '甲题')
            self.assertEqual(len(session.exec(select(Question)).all()), 3)

    def test_rebuild_rejects_missing_existing_question_without_changing_bank(self):
        self.write_questions('甲题', '乙题')
        pipeline.run(self.seed)
        self.write_questions('乙题', '丙题')

        with self.assertRaisesRegex(ValueError, '缺少'):
            pipeline.run(self.seed, rebuild=True)

        with Session(self.engine) as session:
            self.assertEqual({q.content for q in session.exec(select(Question))}, {'甲题', '乙题'})
