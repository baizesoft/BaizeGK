import json

from sqlmodel import Session, select

from app.study_models import StudyDocument


def read(session: Session, key: str):
    record = session.get(StudyDocument, key)
    return json.loads(record.payload) if record else None


def put(session: Session, key: str, value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
    record = session.get(StudyDocument, key)
    if record:
        record.payload = payload
    else:
        session.add(StudyDocument(key=key, payload=payload))


def items(session: Session, prefix: str):
    records = session.exec(select(StudyDocument).where(StudyDocument.key.startswith(prefix)).order_by(StudyDocument.key)).all()
    return [json.loads(record.payload) for record in records]
