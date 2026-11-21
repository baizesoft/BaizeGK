"""Practice through the existing question and attempt tables, with immutable pack identities."""
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import get_session
from app.exam_schedule import CST, check_track
from app.models import Question, QuestionAttempt
from app.study_models import StudyAttempt, StudyQuestion
from app.study_store import items, put, read

router = APIRouter()


class PackQuestion(BaseModel):
    number: str = Field(pattern=r'^[\w.-]{1,24}$')
    prompt: str = Field(min_length=1, max_length=12000)
    options: dict[Literal['A', 'B', 'C', 'D', 'E', 'F'], str] = Field(min_length=2, max_length=6)
    module: str = Field(default='', max_length=32)
    answer: str = ''
    answer_status: Literal['verified', 'unknown'] = 'unknown'
    explanation: str = Field(default='', max_length=12000)
    locator: str = Field(default='', max_length=300)

    @model_validator(mode='after')
    def check_answer(self):
        if (not self.prompt.strip() or any(not value.strip() or len(value) > 4000 for value in self.options.values())
                or (self.answer_status == 'verified' and self.answer not in self.options)
                or (self.answer_status == 'unknown' and (self.answer or self.explanation))):
            raise ValueError('请核对题干、选项和参考答案状态；待核对题不应携带未经确认的答案或解析')
        return self


class Pack(BaseModel):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9_-]{1,63}$')
    region: Literal['gz-tr', 'cq']
    year: int | None = Field(default=None, ge=2000, le=2100)
    title: str = Field(min_length=1, max_length=150)
    variant: str | None = Field(default=None, max_length=80)
    kind: Literal['user_material', 'fixture']
    source: str = Field(min_length=1, max_length=600)
    questions: list[PackQuestion] = Field(min_length=1, max_length=180)

    @model_validator(mode='after')
    def unique_numbers(self):
        if len({q.number for q in self.questions}) != len(self.questions) or not self.title.strip() or not self.source.strip():
            raise ValueError('题号不能重复，卷名和出处不能为空')
        return self


@router.post('/packs')
def import_pack(body: Pack, session: Session = Depends(get_session)):
    record = body.model_dump(exclude={'questions'})
    ordered = sorted(body.questions, key=lambda q: (not q.number.isdecimal(), int(q.number) if q.number.isdecimal() else 0, q.number))
    digest = sha256(json.dumps([record, [q.model_dump() for q in ordered]], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    key = 'pack:' + body.id
    if previous := read(session, key):
        if digest != previous['digest']:
            raise HTTPException(409, '同一卷 ID 已有不同内容；修订卷须用新 ID，不能覆盖既有作答')
        return {'created': False, 'id': body.id}
    for q in ordered:
        # Metadata packs are isolated from the legacy PDF pipeline's real-question rebuild/backfill.
        entry = Question(subject='行测', module=q.module, content=q.prompt, options=json.dumps(q.options, ensure_ascii=False),
                         source=f'学习卷 {body.id} · 第 {q.number} 题', is_real=False,
                         answer=q.answer, analysis=q.explanation)
        session.add(entry)
        session.flush()
        session.add(StudyQuestion(pack_id=body.id, number=q.number, question_id=entry.id, answer_status=q.answer_status,
                                  locator=q.locator or f'{body.source} · 第 {q.number} 题'))
    put(session, key, dict(record, digest=digest, subject='行测', count=len(ordered),
                          numbers=[q.number for q in ordered], verified=sum(q.answer_status == 'verified' for q in ordered)))
    session.commit()
    return {'created': True, 'id': body.id}


@router.get('/packs')
def list_packs(region: str, variant: str | None = None, session: Session = Depends(get_session)):
    check_track(region)
    rows = [r for r in items(session, 'pack:') if r['region'] == region]
    return {'items': [{k: v for k, v in r.items() if k not in {'digest', 'numbers'}} for r in rows
                      if variant is None or (r['variant'] or '未知') == variant],
            'variants': sorted({r['variant'] or '未知' for r in rows})}


class StartRun(BaseModel):
    pack_id: str
    minutes: int = Field(ge=1, le=180)
    slow_seconds: int = Field(default=90, ge=1, le=3600)


class Answer(BaseModel):
    number: str
    chosen: str = Field(min_length=1, max_length=1)
    guessed: bool = False


def load(session, key):
    value = read(session, key)
    if value is None:
        raise HTTPException(404, '记录不存在')
    return value


def relations(session, pack_id):
    joined = session.exec(select(StudyQuestion, Question).join(Question, StudyQuestion.question_id == Question.id)
                          .where(StudyQuestion.pack_id == pack_id)).all()
    return {rel.number: (rel, q) for rel, q in joined}


def run_view(session, record):
    pack = load(session, 'pack:' + record['pack_id'])
    rels = relations(session, pack['id'])
    saved = session.exec(select(StudyAttempt).where(StudyAttempt.run_id == record['id'])).all()
    attempts = {answer['number']: answer for row in saved if (answer := json.loads(row.snapshot))}
    closed = bool(record.get('finished')) or datetime.now(CST) >= datetime.fromisoformat(record['deadline'])
    return {'id': record['id'], 'pack_id': pack['id'], 'title': pack['title'], 'kind': pack['kind'], 'region': pack['region'],
            'source': pack['source'], 'deadline': record['deadline'], 'closed': closed,
            'remaining': 0 if closed else max(0, math.ceil((datetime.fromisoformat(record['deadline']) - datetime.now(CST)).total_seconds())),
            'questions': [{'number': n, 'prompt': rels[n][1].content, 'options': json.loads(rels[n][1].options),
                           'module': rels[n][1].module, 'source': rels[n][0].locator} for n in pack['numbers'] if n in rels],
            'attempts': attempts, 'graded': sum(a['correct'] is not None for a in attempts.values()),
            'correct': sum(a['correct'] is True for a in attempts.values())}


@router.post('/runs')
def start_run(body: StartRun, session: Session = Depends(get_session)):
    load(session, 'pack:' + body.pack_id)
    uid = uuid4().hex
    now = datetime.now(CST)
    record = dict(id=uid, pack_id=body.pack_id, started=now.isoformat(), slow_seconds=body.slow_seconds,
                  deadline=(now + timedelta(minutes=body.minutes)).isoformat(), focused={})
    put(session, 'run:' + uid, record)
    session.commit()
    return run_view(session, record)


@router.get('/runs')
def list_runs(region: str, session: Session = Depends(get_session)):
    check_track(region)
    packs = {r['id']: r for r in items(session, 'pack:') if r['region'] == region}
    return {'items': [{'id': r['id'], 'title': packs[r['pack_id']]['title'], 'started': r['started'],
                       'kind': packs[r['pack_id']]['kind']}
                      for r in sorted(items(session, 'run:'), key=lambda x: x['started'], reverse=True)
                      if r['pack_id'] in packs][:50]}


@router.get('/runs/{uid}')
def get_run(uid: str, session: Session = Depends(get_session)):
    return run_view(session, load(session, 'run:' + uid))


def active(record):
    if record.get('finished') or datetime.now(CST) >= datetime.fromisoformat(record['deadline']):
        raise HTTPException(409, '练习已结束；已提交作答仍可复盘')


@router.put('/runs/{uid}/focus/{number}')
def focus_question(uid: str, number: str, session: Session = Depends(get_session)):
    record = load(session, 'run:' + uid)
    active(record)
    if not session.get(StudyQuestion, (record['pack_id'], number)):
        raise HTTPException(404, '题目不存在')
    if number not in record['focused']:
        record['focused'][number] = datetime.now(CST).isoformat()
        put(session, 'run:' + uid, record)
        session.commit()
    return {'focused': True}


@router.post('/runs/{uid}/answers')
def submit_answer(uid: str, body: Answer, session: Session = Depends(get_session)):
    record = load(session, 'run:' + uid)
    before = run_view(session, record)
    if body.number in before['attempts']:
        saved = before['attempts'][body.number]
        if saved['chosen'] == body.chosen and saved['guessed'] == body.guessed:
            return before
        raise HTTPException(409, '本题已提交；复盘保留首次作答')
    active(record)
    relation = session.get(StudyQuestion, (record['pack_id'], body.number))
    question = session.get(Question, relation.question_id) if relation else None
    if not relation or not question or body.chosen not in json.loads(question.options):
        raise HTTPException(422, '题号或选项无效')
    if body.number not in record['focused']:
        raise HTTPException(409, '请先打开题目')
    now = datetime.now(CST)
    seconds = max(0, math.floor((now - datetime.fromisoformat(record['focused'][body.number])).total_seconds()))
    support = relation.answer_status == 'verified'
    correct = body.chosen == question.answer if support else None
    attempt = QuestionAttempt(question_id=question.id, chosen=body.chosen, time_sec=seconds, is_correct=correct)
    session.add(attempt)
    session.flush()
    slow = seconds >= record['slow_seconds']
    snapshot = dict(number=body.number, chosen=body.chosen, guessed=body.guessed, slow=slow, seconds=seconds,
                    correct=correct, reference=question.answer if support else None, prompt=question.content,
                    options=json.loads(question.options), source=relation.locator, explanation=question.analysis if support else '',
                    tags=[label for include, label in ((correct is False, '错题'), (correct is True and body.guessed, '蒙对'),
                                                       (slow, '超时'), (not support, '答案待核对')) if include])
    session.add(StudyAttempt(attempt_id=attempt.id, run_id=uid, number=body.number, guessed=body.guessed, slow=slow,
                             snapshot=json.dumps(snapshot, ensure_ascii=False)))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, '已有作答，请重新读取') from None
    return run_view(session, record)


@router.put('/runs/{uid}/finish')
def finish_run(uid: str, session: Session = Depends(get_session)):
    record = load(session, 'run:' + uid)
    if not record.get('finished'):
        record['finished'] = datetime.now(CST).isoformat()
        put(session, 'run:' + uid, record)
        session.commit()
    return run_view(session, record)
