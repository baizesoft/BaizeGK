"""Local-only records added alongside the legacy question and attempt tables."""
from sqlmodel import Field, SQLModel, UniqueConstraint


class StudyDocument(SQLModel, table=True):
    key: str = Field(primary_key=True)
    payload: str


class StudyQuestion(SQLModel, table=True):
    pack_id: str = Field(primary_key=True)
    number: str = Field(primary_key=True)
    question_id: int = Field(foreign_key='question.id', unique=True)
    answer_status: str
    locator: str


class StudyAttempt(SQLModel, table=True):
    __table_args__ = (UniqueConstraint('run_id', 'number'),)
    attempt_id: int = Field(primary_key=True, foreign_key='questionattempt.id')
    run_id: str = Field(index=True)
    number: str
    guessed: bool = False
    slow: bool = False
    snapshot: str
