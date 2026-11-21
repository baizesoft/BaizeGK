"""Read local official XLSX/CSV exports; ambiguous rules remain explicitly unresolved."""
import base64
import binascii
import csv
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import PurePath
import re
from typing import Literal
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from fastapi import APIRouter, Depends, HTTPException, Query
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from xlrd import open_workbook
from xlrd.biffh import XLRDError
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.database import get_session
from app.exam_schedule import CURRENT_YEAR, check_track, valid_source
from app.study_practice import load
from app.study_store import items, put, read

router = APIRouter()
MAX_FILE = 8 * 1024 * 1024
MAX_ROWS = 9000
ALIASES = {
    'title': ('职位名称', '招考职位', '职位', '岗位名称', '招录职位', '招录职位名称'),
    'area': ('地区', '地区部门', '考区', '区县', '市州', '工作地点', '招录地区'),
    'unit': ('招录单位', '招录机关', '招录机关单位', '招录机关（单位）', '招考单位', '单位名称'),
    'code': ('职位代码', '职位编码', '职位编号', '岗位代码'),
    'degree': ('学历', '学历要求'), 'major': ('专业', '专业要求'), 'age': ('年龄', '年龄要求'),
    'variant': ('申论考试类型', '申论类别', '考试类别', '申论考试科目', '所属小类'),
}
NO_LIMIT = {'不限', '无', '无要求', '不要求', '否', '—', '-', '不限制', '无限制'}
DEGREES = {'大专': 0, '专科': 0, '本科': 1, '硕士': 2, '博士': 3}
MAJOR_LEVELS = {'大专', '专科', '本科', '研究生'}
# The published Guizhou announcement uses a QR attachment on a third-party CDN.
# Only this verified pair is allowed; arbitrary links on those hosts are not trusted.
GUIZHOU_2026_NOTICE = 'https://www.tongren.gov.cn/2026/0117/343673.shtml'
GUIZHOU_2026_ATTACHMENTS = {
    'https://qr61.cn/oWgwv2/qkbTLKF',
    'https://ncstatic.clewm.net/rsrc/2026/0116/21/7c230a3f517d6498df1a8a9526913d39.xls',
}


class TableImport(BaseModel):
    region: Literal['gz-tr', 'cq']
    year: int = Field(ge=2000, le=2100)
    kind: Literal['official', 'fixture']
    filename: str = Field(min_length=5, max_length=200)
    announcement: str = Field(min_length=8, max_length=600)
    file_url: str = Field(default='', max_length=600)
    content: str = Field(min_length=4, max_length=11_184_812)


def clean(x):
    return str(x).strip() if x is not None else ''


def normalized(x):
    return re.sub(r'\s+', '', clean(x))


def tables(data, suffix):
    if suffix == '.xls':
        book = open_workbook(file_contents=data, on_demand=True)
        try:
            def numbered(sheet):
                if sheet.nrows > MAX_ROWS + 300 or sheet.ncols > 100:
                    raise ValueError('表格超过行列限制')
                return ((i + 1, sheet.row_values(i)) for i in range(sheet.nrows))
            return extract((sheet.name, numbered(sheet)) for sheet in book.sheets())
        finally:
            book.release_resources()
    if suffix == '.csv':
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = data.decode('gb18030')
        stream = csv.reader(StringIO(text, newline=''), strict=True)
        def physical_rows():
            last = 0
            for row in stream:
                yield last + 1, row
                last = stream.line_num
        return extract([('CSV', physical_rows())])
    with ZipFile(BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) > 300 or sum(m.file_size for m in members) > 36 * 1024 * 1024:
            raise ValueError('工作簿展开后超过限制')
        if any(m.filename.startswith(('xl/externalLinks/', 'xl/vbaProject')) for m in members):
            raise ValueError('不接受包含外部工作簿链接或宏的文件')
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True, keep_links=False)
    try:
        return extract((sheet.title, enumerate(sheet.iter_rows(max_col=100, values_only=True), 1)) for sheet in workbook.worksheets)
    finally:
        workbook.close()


def extract(sheets):
    records, years, visited = [], set(), 0
    for name, stream in sheets:
        mapping = None
        headers, extra = [], []
        grouped: dict[str, int] = {}
        extra_labels: dict[int, str] = {}
        awaiting_subheaders = True
        for number, row in stream:
            visited += 1
            if len(row) > 100 or visited > MAX_ROWS + 300:
                raise ValueError('表格超过行列限制')
            if mapping is None:
                if number > 24:
                    break
                for cell in row:
                    years.update(int(x) for x in re.findall(r'(20\d\d)年度.{0,34}职位', clean(cell)))
                headers = [normalized(x) for x in row]
                found = {field: next((i for i, x in enumerate(headers) if x in aliases), None)
                         for field, aliases in ALIASES.items()}
                if found['title'] is not None and (found['degree'] is not None or found['major'] is not None):
                    mapping = found
                    extra = [i for i, x in enumerate(headers) if i not in mapping.values() and any(
                        k in x for k in ('要求', '工作经历', '服务基层', '政治面貌', '户籍', '应届', '条件', '性别', '学位', '备注', '资格', '证书', '需要说明'))]
                continue
            def cell(i):
                return clean(row[i])[:3000] if i is not None and i < len(row) else ''
            fields = {key: cell(i) for key, i in mapping.items()}
            if awaiting_subheaders:
                awaiting_subheaders = False
                if not fields['title'] and fields['major'] in MAJOR_LEVELS and (major_index := mapping['major']) is not None:
                    for i in range(major_index, len(headers)):
                        if i != major_index and headers[i]:
                            break
                        if cell(i) in MAJOR_LEVELS:
                            grouped[cell(i)] = i
                if not fields['title']:
                    for i, header in enumerate(headers):
                        if '定向招录' not in header:
                            continue
                        for j in range(i, len(headers)):
                            if j != i and headers[j]:
                                break
                            if cell(j):
                                extra_labels[j] = cell(j)
            if not fields['title'] or fields['title'] in ALIASES['title']:
                continue
            by_degree = {level: cell(i) for level, i in grouped.items()}
            if grouped:
                fields['major'] = '；'.join(f'{k}：{v or "未填"}' for k, v in by_degree.items())
            raw = {extra_labels.get(i, headers[i] or f'第{i + 1}列'): cell(i)
                   for i in sorted(set(extra) | extra_labels.keys()) if cell(i)}
            records.append(dict(fields, sheet=name, row=number, conditions=raw, major_by_degree=by_degree))
            if len(records) > MAX_ROWS:
                raise ValueError('表格职位过多，请按官方工作表分批导入')
    if not records:
        raise ValueError('未识别到职位列和学历或专业列；请用包含官方列名的 XLSX / CSV')
    return records, years


def safe_url(value, region):
    if not valid_source(value, region):
        raise HTTPException(422, '请填写对应地区的官方 HTTPS 公告或附件地址')


@router.post('/jobs/import')
def ingest_jobs(body: TableImport, session: Session = Depends(get_session)):
    safe_url(body.announcement, body.region)
    if body.file_url:
        if not (body.region == 'gz-tr' and body.year == 2026 and body.announcement == GUIZHOU_2026_NOTICE
                and body.file_url in GUIZHOU_2026_ATTACHMENTS):
            safe_url(body.file_url, body.region)
    elif body.kind == 'official':
        raise HTTPException(422, '官方表格须保留附件原地址')
    if body.kind == 'official' and re.search(fr'/{body.year - 1}/0[1-6](?:/|\d)', body.announcement):
        raise HTTPException(422, '公告链接疑似属于上一轮，请核对年度')
    suffix = PurePath(body.filename).suffix.lower()
    if suffix not in ('.csv', '.xlsx', '.xls'):
        raise HTTPException(422, '仅支持 XLS / XLSX / CSV')
    try:
        data = base64.b64decode(body.content, validate=True)
        if len(data) > MAX_FILE:
            raise ValueError('表格最多 8 MiB')
        meta = body.model_dump(exclude={'content'})
        uid = sha256((str(sorted(meta.items())) + '\n').encode() + data).hexdigest()[:24]
        if old := read(session, 'jobs:' + uid):
            return summary(old)
        rows, years = tables(data, suffix)
        if years and years != {body.year}:
            raise ValueError('工作簿标题年度与填写年度不一致')
    except (ValueError, UnicodeError, csv.Error, binascii.Error, BadZipFile, InvalidFileException, XLRDError,
            ParseError, DefusedXmlException, KeyError, OSError) as exc:
        raise HTTPException(422, '读表失败：' + str(exc)[:160]) from None
    table = dict(meta, id=uid, count=len(rows), rows=rows)
    put(session, 'jobs:' + uid, table)
    session.commit()
    return summary(table)


def summary(table):
    return {**{k: v for k, v in table.items() if k != 'rows'},
            'reference_only': table['year'] != CURRENT_YEAR or table['kind'] == 'fixture'}


@router.get('/jobs')
def list_tables(region: str, session: Session = Depends(get_session)):
    check_track(region)
    return {'items': [summary(x) for x in items(session, 'jobs:') if x['region'] == region]}


def judge(row, degree, major, age):
    issues = []
    education, program, years = (normalized(row[k]) for k in ('degree', 'major', 'age'))
    if levels := row.get('major_by_degree'):
        level = '大专' if degree in ('专科', '大专') else '研究生' if degree in ('硕士', '博士') else degree
        program = normalized(levels.get(level) or (levels.get('专科') if level == '大专' else ''))
    if education not in NO_LIMIT:
        m = re.fullmatch(r'(?:大学)?(大专|专科|本科|硕士|博士)(?:研究生)?(及以上|以上)?', education)
        if education == '研究生' and degree and DEGREES[degree] < DEGREES['硕士']:
            return None
        if education == '研究生' and degree:
            education = '不限'  # graduate level matched; specific degree remains in the source conditions
        if education == '不限':
            pass
        elif not degree or not m:
            issues.append('学历要求需核对')
        elif (DEGREES[degree] < DEGREES[m[1]] if m[2] else (DEGREES[degree] != DEGREES[m[1]])):
            return None
    if program not in NO_LIMIT:
        exact = normalized(major)
        listed = {re.sub(r'^\d{4,8}(?=[^\d])', '', x) for x in re.split(r'[、，,；;\n]+', program)}
        if not exact or exact not in listed:
            issues.append('专业、专业类或目录需核实')
    if years not in NO_LIMIT:
        compact = years.replace('周岁', '').replace('岁', '')
        rng = re.fullmatch(r'(\d{2})(?:-|—|–|至|~|～)(\d{2})', compact)
        limit = re.fullmatch(r'(\d{2})(?:及)?以下', compact)
        if age is None or not (rng or limit):
            issues.append('年龄按公告及出生年月核实')
        elif rng and not int(rng[1]) <= age <= int(rng[2]) or limit and age > int(limit[1]):
            return None
        else:
            # Even a numeric provisional match is not a DOB/qualification ruling.
            if limit and age == int(limit[1]):
                issues.append('年龄卡边界，查公告出生年月')
    issues.extend(k + '需核对' for k, v in row['conditions'].items() if normalized(v) not in NO_LIMIT)
    return issues


@router.get('/jobs/{uid}')
def filter_jobs(uid: str, area: str = '', area_only: bool = False, degree: Literal['大专', '专科', '本科', '硕士', '博士'] | None = None,
                major: str = '', strict_major: bool = False, condition: str = '',
                age: int | None = Query(None, ge=16, le=75), page: int = Query(1, ge=1),
                session: Session = Depends(get_session)):
    table = load(session, 'jobs:' + uid)
    meta = summary(table)
    matches = []
    for row in table['rows']:
        if area.strip() and not any(area.strip() in row[key] for key in (('area',) if area_only else ('area', 'unit'))):
            continue
        if condition.strip() and not any(condition.strip() in f'{k} {v}' for k, v in row['conditions'].items()):
            continue
        issues = judge(row, degree, major, age)
        if issues and strict_major and major.strip() and '专业、专业类或目录需核实' in issues:
            continue
        if issues is not None:
            matches.append(dict(row, status='需核实' if issues else '初筛匹配', reasons=issues,
                                reference_only=meta['reference_only']))
    start = (page - 1) * 50
    return dict(table=meta, items=matches[start:start + 50], total=len(matches), page=page, page_size=50,
                notice='初筛不等于报考资格；报名前按公告原文和招录单位口径核对。')
