from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.exam_schedule import ExamEdit, check_track, dashboard
from app.study_jobs import router as jobs_router
from app.study_practice import router as practice_router
from app.study_review import router as review_router
from app.study_store import put, read

router = APIRouter(prefix='/api/study', tags=['study'])
router.include_router(practice_router)
router.include_router(review_router)
router.include_router(jobs_router)


@router.get('/exams')
def list_exams(session: Session = Depends(get_session)):
    return dashboard(lambda key: read(session, key))


@router.put('/exams/{track}')
def save_exam(track: str, body: ExamEdit, session: Session = Depends(get_session)):
    check_track(track)
    put(session, 'exam:' + track, body.validated(track))
    session.commit()
    return list_exams(session)
