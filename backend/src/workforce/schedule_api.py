"""Owner API for inert daily schedule definitions."""
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .models import AuditEvent, OwnerSession, Project, Schedule, ScheduleOccurrence, now
from .security import current_session, require_csrf
from .services import AccessDenied, authorize_agent_project

router = APIRouter()


class ScheduleInput(BaseModel):
    project_id: str
    agent_id: str
    title: str = Field(min_length=1, max_length=240)
    timezone: str = Field(min_length=1, max_length=100)
    local_time: str = Field(pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
    root_cap: Decimal = Field(ge=Decimal('0.010000'), max_digits=12, decimal_places=6)


def detail(row: Schedule) -> dict:
    return {'id': row.id, 'project_id': row.project_id, 'agent_id': row.agent_id,
            'title': row.title, 'timezone': row.timezone,
            'local_time': f'{row.local_hour:02d}:{row.local_minute:02d}',
            'root_cap': row.root_cap, 'enabled': row.enabled,
            'revision': row.revision, 'created_at': row.created_at,
            'last_checked_at': row.last_checked_at}


class ScheduleStateInput(BaseModel):
    enabled: bool
    expected_revision: int = Field(ge=1)


@router.get('/api/schedules')
def list_schedules(project_id: str, _: OwnerSession = Depends(current_session),
                   db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(Schedule).where(Schedule.project_id == project_id)
                      .order_by(Schedule.created_at, Schedule.id)).all()
    return [detail(row) for row in rows]


@router.post('/api/schedules', status_code=201)
def create_schedule(data: ScheduleInput, session: OwnerSession = Depends(require_csrf),
                    db: Session = Depends(db_session)):
    if db.get(Project, data.project_id) is None:
        raise HTTPException(404, 'Project not found')
    try:
        authorize_agent_project(db, data.agent_id, data.project_id, 'project.execute')
    except AccessDenied as exc:
        raise HTTPException(403, 'Project access denied') from exc
    try:
        ZoneInfo(data.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(422, 'Unknown IANA timezone') from exc
    hour, minute = (int(part) for part in data.local_time.split(':'))
    row = Schedule(project_id=data.project_id, agent_id=data.agent_id,
                   title=data.title, timezone=data.timezone, local_hour=hour,
                   local_minute=minute, root_cap=data.root_cap, enabled=False,
                   revision=1)
    db.add(row)
    db.flush()
    db.add(AuditEvent(actor=session.owner_id, action='schedule.create',
                      resource=row.id, outcome='allowed',
                      detail={'project_id': data.project_id, 'agent_id': data.agent_id}))
    db.commit()
    return detail(row)


@router.post('/api/schedules/{schedule_id}/state')
def set_schedule_state(schedule_id: str, data: ScheduleStateInput,
                       session: OwnerSession = Depends(require_csrf),
                       db: Session = Depends(db_session)):
    row = db.execute(select(Schedule).where(Schedule.id == schedule_id)
                     .with_for_update()).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, 'Schedule not found')
    if row.revision != data.expected_revision:
        raise HTTPException(409, 'Schedule revision changed')
    if data.enabled:
        try:
            authorize_agent_project(db, row.agent_id, row.project_id, 'project.execute')
        except AccessDenied as exc:
            raise HTTPException(403, 'Project access denied') from exc
    row.enabled = data.enabled
    row.last_checked_at = now()
    row.revision += 1
    db.add(AuditEvent(actor=session.owner_id, action='schedule.state',
                      resource=row.id, outcome='allowed',
                      detail={'enabled': data.enabled, 'revision': row.revision}))
    db.commit()
    return detail(row)


@router.get('/api/schedules/{schedule_id}/occurrences')
def list_occurrences(schedule_id: str, _: OwnerSession = Depends(current_session),
                     db: Session = Depends(db_session)):
    if db.get(Schedule, schedule_id) is None:
        raise HTTPException(404, 'Schedule not found')
    rows = db.scalars(select(ScheduleOccurrence).where(
        ScheduleOccurrence.schedule_id == schedule_id).order_by(
        ScheduleOccurrence.local_date.desc()).limit(100)).all()
    return [{'id': row.id, 'local_date': row.local_date,
             'scheduled_for': row.scheduled_for, 'status': row.status,
             'reason': row.reason, 'execution_id': row.execution_id}
            for row in rows]
