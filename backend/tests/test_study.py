import base64
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import create_engine

from app import database
from app.main import app


class StudyTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        engine = create_engine(f'sqlite:///{(Path(temp.name) / "study.db").as_posix()}')
        self.addCleanup(engine.dispose)
        override = patch.object(database, 'engine', engine)
        override.start()
        self.addCleanup(override.stop)
        self.client = self.enterContext(TestClient(app))

    def request(self, method, path, **kwargs):
        response = self.client.request(method, '/api/study' + path, **kwargs)
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def source(self, exam):
        if exam == 'gz-tr':
            return 'https://www.tongren.gov.cn/'
        return 'https://rlsbj.cq.gov.cn/ywzl/rsks/gwyks/'

    def set_exam(self, exam, start, end, status='confirmed', year=2027):
        return self.client.put('/api/study/exams/' + exam, json={
            'year': year, 'status': status, 'source': self.source(exam),
            'source_title': f'{"贵州" if exam == "gz-tr" else "重庆"}{year}年度常规公务员招录公告（测试）',
            'timeline': {'written': {'start': start, 'end': end}} if start else {},
        })

    def test_exams_keep_history_and_failed_checks_out_of_current_dates(self):
        initial = self.request('GET', '/exams')
        self.assertEqual([e['id'] for e in initial['items']], ['gz-tr', 'cq'])
        self.assertEqual(initial['collision'], 'unknown')
        self.assertNotIn('written', initial['items'][0]['current']['timeline'])
        self.assertIn('written', initial['items'][0]['history']['timeline'])
        spoof = self.client.put('/api/study/exams/gz-tr', json={
            'year': 2027, 'status': 'confirmed', 'source': initial['items'][0]['history']['source'],
            'source_title': '贵州2027年度公务员招录公告',
        })
        self.assertEqual(spoof.status_code, 422)
        self.assertEqual(self.set_exam('gz-tr', '2026-03-14T09:00', '2026-03-14T16:30').status_code, 422)
        self.assertEqual(self.set_exam('gz-tr', None, None, year=2026).status_code, 422)
        self.assertEqual(self.set_exam('gz-tr', None, None, status='unverified').status_code, 200)
        result = self.request('GET', '/exams')
        self.assertEqual(result['items'][0]['current']['status'], 'unverified')
        self.assertEqual(result['collision'], 'unknown')

    def test_actual_overlap_not_just_same_day(self):
        self.assertEqual(self.set_exam('gz-tr', '2027-03-14T09:00', '2027-03-14T11:00').status_code, 200)
        self.assertEqual(self.set_exam('cq', '2027-03-14T11:00', '2027-03-14T13:00').status_code, 200)
        self.assertEqual(self.request('GET', '/exams')['collision'], 'none')
        self.assertEqual(self.set_exam('cq', '2027-03-14T10:00', '2027-03-14T13:00').status_code, 200)
        self.assertEqual(self.request('GET', '/exams')['collision'], 'overlap')

    def pack(self, region='cq'):
        return {'id': region + '-sample', 'region': region, 'year': 2026, 'kind': 'fixture',
                'title': '技术验收测试卷', 'variant': '综合', 'source': '仅用于回归的合成题',
                'questions': [
                    {'number': '1', 'prompt': '测试：一加一？', 'options': {'A': '二', 'B': '三'}, 'answer': 'A', 'answer_status': 'verified'},
                    {'number': '2', 'prompt': '测试：无核对答案', 'options': {'A': '甲', 'B': '乙'}, 'answer_status': 'unknown'}]}

    def test_regional_import_timer_grading_and_history(self):
        pack = self.pack('gz-tr')
        self.assertTrue(self.request('POST', '/packs', json=pack)['created'])
        self.assertTrue(self.request('POST', '/packs', json=self.pack())['created'])
        packs = self.request('GET', '/packs', params={'region': 'gz-tr', 'variant': '综合'})['items']
        self.assertEqual([x['id'] for x in packs], [pack['id']])
        run = self.request('POST', '/runs', json={'pack_id': pack['id'], 'minutes': 10})
        self.assertNotIn('answer', run['questions'][0])
        self.assertGreater(run['remaining'], 0)
        for number, choice in [('1', 'B'), ('2', 'A')]:
            self.request('PUT', f"/runs/{run['id']}/focus/{number}")
            result = self.request('POST', f"/runs/{run['id']}/answers", json={'number': number, 'chosen': choice})
        self.assertEqual((result['graded'], result['correct']), (1, 0))
        self.assertIsNone(result['attempts']['2']['correct'])
        pack['questions'].reverse()
        self.assertFalse(self.request('POST', '/packs', json=pack)['created'])
        result = self.request('GET', f"/runs/{run['id']}")
        self.assertEqual(result['attempts']['1']['prompt'], '测试：一加一？')
        changed = self.pack('gz-tr')
        changed['questions'][0]['prompt'] = '测试：已修改题干'
        self.assertEqual(self.client.post('/api/study/packs', json=changed).status_code, 409)

    def test_essay_persists_and_review_prompt_uses_material(self):
        doc = self.request('POST', '/essays', json={
            'id': 'gz-essay-test', 'region': 'gz-tr', 'title': '申论测试', 'kind': 'fixture',
            'source': '合成材料', 'materials': ['工作人员记录了排队现象。'], 'question': '概括问题。'})
        self.request('PUT', f"/essays/{doc['id']}/answer", json={'answer': '排队时间较长。'})
        reread = self.request('GET', f"/essays/{doc['id']}")
        self.assertEqual(reread['answer'], '排队时间较长。')
        prompt = self.request('GET', f"/essays/{doc['id']}/review")
        self.assertIn('材料 1：工作人员记录了排队现象。', prompt['text'])
        self.assertIn('不提供官方分', prompt['text'])
        self.assertFalse(prompt['in_app_ai'])

    def test_guessed_and_slow_review_without_altering_grade(self):
        self.request('POST', '/packs', json=self.pack())
        run = self.request('POST', '/runs', json={'pack_id': 'cq-sample', 'minutes': 10, 'slow_seconds': 1})
        with patch('app.study_practice.datetime') as clock:
            from datetime import datetime, timedelta
            clock.fromisoformat = datetime.fromisoformat
            clock.now.side_effect = lambda tz: datetime.now(tz) - timedelta(seconds=4)
            self.request('PUT', f"/runs/{run['id']}/focus/1")
        result = self.request('POST', f"/runs/{run['id']}/answers", json={'number': '1', 'chosen': 'A', 'guessed': True})
        self.assertEqual(result['attempts']['1']['tags'], ['蒙对', '超时'])
        prompt = self.request('GET', f"/runs/{run['id']}/review")
        self.assertIn('不要推断我的错因', prompt['text'])
        self.assertEqual(self.request('GET', f"/runs/{run['id']}")['correct'], 1)

    def test_server_enforces_deadline_and_retains_earlier_work(self):
        from datetime import datetime, timedelta

        self.request('POST', '/packs', json=self.pack())
        r = self.request('POST', '/runs', json={'pack_id': 'cq-sample', 'minutes': 1})
        prefix = f"/runs/{r['id']}"
        self.request('PUT', prefix + '/focus/1')
        self.request('POST', prefix + '/answers', json={'number': '1', 'chosen': 'A'})
        self.request('PUT', prefix + '/focus/2')
        with patch('app.study_practice.datetime') as clock:
            clock.fromisoformat = datetime.fromisoformat
            clock.now.side_effect = lambda tz: datetime.now(tz) + timedelta(minutes=2)
            self.assertEqual(self.client.post('/api/study' + prefix + '/answers', json={'number': '2', 'chosen': 'B'}).status_code, 409)
            reopened = self.request('GET', prefix)
            self.assertTrue(reopened['closed'])
            self.assertEqual(list(reopened['attempts']), ['1'])

    def test_jobs_filter_is_conservative_and_keeps_physical_row(self):
        csv = '职位表测试\n地区,职位名称,学历,专业,年龄,其他要求,单位名称\n江北,信息岗,本科及以上,计算机类,35周岁以下,两年基层经历,信息中心\n渝中,管理岗,本科及以上,不限,18-38周岁,无,江北驻点单位\n'
        payload = {'region': 'cq', 'year': 2026, 'kind': 'fixture', 'filename': 'sample.csv',
                   'announcement': 'https://www.cqyz.gov.cn/zwgk/example.html', 'file_url': '',
                   'content': base64.b64encode(csv.encode()).decode()}
        table = self.request('POST', '/jobs/import', json=payload)
        self.assertEqual(table['count'], 2)
        rows = self.request('GET', f"/jobs/{table['id']}", params={
            'degree': '本科', 'major': '计算机科学与技术', 'age': 34})['items']
        self.assertEqual([r['row'] for r in rows], [3, 4])
        self.assertEqual(rows[0]['status'], '需核实')
        self.assertEqual(rows[1]['status'], '初筛匹配')
        self.assertTrue(all(r['reference_only'] for r in rows))
        narrowed = self.request('GET', f"/jobs/{table['id']}", params={'age': 36})['items']
        self.assertEqual([r['row'] for r in narrowed], [4])
        strict = self.request('GET', f"/jobs/{table['id']}", params={'major': '计算机科学与技术', 'strict_major': True})['items']
        self.assertEqual([r['row'] for r in strict], [4])
        extra = self.request('GET', f"/jobs/{table['id']}", params={'condition': '基层经历'})['items']
        self.assertEqual([r['row'] for r in extra], [3])
        by_area = self.request('GET', f"/jobs/{table['id']}", params={'area': '江北', 'area_only': True})['items']
        self.assertEqual([r['row'] for r in by_area], [3])

    def test_grouped_guizhou_headers_do_not_mix_degree_levels_or_hide_conditions(self):
        from app.study_jobs import extract, judge
        rows, _ = extract([('公务员职位表', enumerate([
            ('考区', '职位名称', '学历要求', '专业要求', '', '', '定向招录项目要求', ''),
            ('', '', '', '大专', '本科', '研究生', '服务基层项目人员', '2026届毕业生'),
            ('铜仁市', '信息岗', '本科及以上', '无限制', '080901计算机科学与技术', '0812计算机科学与技术类', '否', '是'),
        ], 1))])
        self.assertEqual(rows[0]['row'], 3)
        self.assertIn('2026届毕业生需核对', judge(rows[0], '本科', '计算机科学与技术', 30))
        self.assertNotIn('专业、专业类或目录需核实', judge(rows[0], '本科', '计算机科学与技术', 30))
        self.assertIn('专业、专业类或目录需核实', judge(rows[0], '硕士', '计算机科学与技术', 30))
