from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db_session
from app.repositories.events import EventRepository
from app.repositories.runs import RunRepository
from app.schemas.event import EventRead
from app.schemas.run import RunRead

router = APIRouter(prefix="/api")


@router.get("/runs", response_model=list[RunRead])
def runs(session: Session = Depends(get_db_session)) -> list[RunRead]:
    run_repo = RunRepository(session)
    return [
        RunRead.model_validate(run, from_attributes=True) for run in run_repo.list_recent(limit=20)
    ]


@router.get("/events", response_model=list[EventRead])
def events(session: Session = Depends(get_db_session)) -> list[EventRead]:
    event_repo = EventRepository(session)
    return [
        EventRead.model_validate(event, from_attributes=True)
        for event in event_repo.list_recent(limit=20)
    ]
