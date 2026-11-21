"""Two local recruitment tracks; no background fetching or application automation."""
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlsplit
import re

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

CST = timezone(timedelta(hours=8))
TRACKS = {'gz-tr': '贵州省考·铜仁岗位', 'cq': '重庆市考'}
CURRENT_YEAR = 2027
PHASES = ('registration', 'payment', 'ticket', 'written', 'written_pm')
PUBLIC = ('written', 'written_pm')
CHECKED = '2026-11-21T14:40:00+08:00'
HOSTS = {
    'gz-tr': ('tongren.gov.cn', 'gzrsks.com.cn', 'guizhou.gov.cn', 'gzrsks.cn'),
    'cq': ('cq.gov.cn', 'cqyz.gov.cn', '12371.gov.cn'),
}


def check_track(track):
    if track not in TRACKS:
        raise HTTPException(404, '未知招录地区')


def valid_source(value, track):
    try:
        u = urlsplit(value)
        host = u.hostname or ''
        valid = u.scheme == 'https' and not u.username and not u.password and u.port in (None, 443)
    except ValueError:
        valid, host = False, ''
    return valid and any(host == h or host.endswith('.' + h) for h in HOSTS[track])


class Period(BaseModel):
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode='after')
    def validate_order(self):
        for key in ('start', 'end'):
            value = getattr(self, key)
            if value is not None:
                setattr(self, key, value.replace(tzinfo=CST) if value.tzinfo is None else value.astimezone(CST))
        if self.start and self.end and self.start >= self.end:
            raise ValueError('结束必须晚于开始')
        return self


class ExamEdit(BaseModel):
    year: int
    status: Literal['pending', 'unverified', 'confirmed']
    source: str = Field(min_length=8, max_length=600)
    source_title: str = Field(max_length=200)
    timeline: dict[Literal['registration', 'payment', 'ticket', 'written', 'written_pm'], Period] = Field(default_factory=dict)

    def validated(self, track):
        if self.year != CURRENT_YEAR or not valid_source(self.source, track):
            raise HTTPException(422, '只能保存本轮年份和对应地区的官方 HTTPS 来源')
        if self.status != 'confirmed' and self.timeline:
            raise HTTPException(422, '尚未核实的日期不能保存成本轮日程')
        if self.status == 'confirmed':
            title = self.source_title.strip()
            target_names = ('贵州', '铜仁') if track == 'gz-tr' else ('重庆',)
            if (not re.search(fr'(?<!\d){self.year}\s*(?:年度|年)', title)
                    or '公务员' not in title or '公告' not in title
                    or not any(name in title for name in target_names)
                    or any(x in title for x in ('中央机关', '国考', '选调', '遴选'))):
                raise HTTPException(422, '确认本轮须填写与地区和年度相符的常规公务员招录公告标题')
            if re.search(fr'/{self.year - 1}/0[1-6](?:/|\d)', urlsplit(self.source).path):
                raise HTTPException(422, '该链接属于上一轮时间范围，请核对正文')
            earliest = datetime(self.year - 1, 7, 1, tzinfo=CST)
            latest = datetime(self.year + 1, 1, 1, tzinfo=CST)
            for period in self.timeline.values():
                if any(not earliest <= x < latest for x in (period.start, period.end) if x):
                    raise HTTPException(422, '日程不属于本轮，请检查是否误用了历史日期')
        return {**self.model_dump(mode='json'), 'checked_at': datetime.now(CST).isoformat()}


BASE = {
    'gz-tr': dict(status='unverified', source='https://www.gzrsks.com.cn/', source_title='贵州人事考试信息网',
                  note='铜仁网旧公告可读；贵州人事考试入口未能核实为有效公告目录，不能据此判定尚未发布。'),
    'cq': dict(status='pending', source='https://rlsbj.cq.gov.cn/ywzl/rsks/gwyks/', source_title='重庆市人社局公务员考试栏目',
               note='该栏目本次未查到 2027 年度常规市考招录公告；这不是对所有公告入口的全面排查。'),
}


def period(start=None, end=None):
    return dict(start=f'{start}+08:00' if start else None, end=f'{end}+08:00' if end else None)


HISTORY = {
    'gz-tr': dict(year=2026, source='https://www.tongren.gov.cn/2026/0117/343673.shtml', timeline={
        'registration': period('2026-01-19T09:00', '2026-01-23T17:00'),
        'payment': period('2026-01-19T09:00', '2026-01-26T17:00'),
        'ticket': period('2026-03-09T09:00', '2026-03-13T17:00'),
        'written': period('2026-03-14T09:00', '2026-03-14T11:00'),
        'written_pm': period('2026-03-14T14:00', '2026-03-14T16:30'),
    }),
    'cq': dict(year=2026, source='https://www.cqyz.gov.cn/zwgk_229/fdzdgknr/zkly_31707/zklm/202601/t20260121_15342499.html', timeline={
        'registration': period('2026-01-20T09:00', '2026-01-25T09:00'),
        'payment': period(end='2026-02-01T09:00'),
        'ticket': period('2026-03-09T09:00', '2026-03-15T09:30'),
        'written': period('2026-03-14T09:00', '2026-03-14T11:00'),
        'written_pm': period('2026-03-14T14:00', '2026-03-14T16:30'),
    }),
}


def phase_status(value, now):
    start, end = (datetime.fromisoformat(value[k]) if value.get(k) else None for k in ('start', 'end'))
    if end and now >= end:
        return '已截止'
    if start and now < start:
        return '未开始'
    if start and end:
        return '进行中'
    return '仅公布部分时间'


def dashboard(read):
    now = datetime.now(CST)
    items = []
    intervals = []
    for track, name in TRACKS.items():
        current: dict[str, Any] = read('exam:' + track) or dict(BASE[track], year=CURRENT_YEAR, checked_at=CHECKED, timeline={})
        timeline = current['timeline'] if current['status'] == 'confirmed' else {}
        spans = [timeline[k] for k in PUBLIC if k in timeline]
        intervals.append([(datetime.fromisoformat(x['start']), datetime.fromisoformat(x['end'])) for x in spans]
                         if spans and all(x.get('start') and x.get('end') for x in spans) else [])
        stages = {k: phase_status(v, now) for k, v in timeline.items() if any(v.values())}
        items.append(dict(id=track, name=name, current=current, history=HISTORY[track], stages=stages))
    collision = 'unknown' if not all(intervals) else ('overlap' if any(
        max(a, c) < min(b, d) for a, b in intervals[0] for c, d in intervals[1]) else 'none')
    return dict(items=items, collision=collision, as_of=now.isoformat())
