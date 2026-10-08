"""Project-scoped, commit-ordered activity and resumable SSE reads."""
import asyncio
import json
import time
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session, session_factory
from .models import OwnerSession, Project, ProjectActivity, ProjectActivityCursor
from .security import current_session

router = APIRouter()


def record_activity(db: Session, *, project_id: str, actor: str, action: str,
                    resource: str, outcome: str) -> ProjectActivity:
    cursor = db.execute(select(ProjectActivityCursor).where(
        ProjectActivityCursor.project_id == project_id).with_for_update()).scalar_one()
    cursor.sequence += 1
    row = ProjectActivity(project_id=project_id, sequence=cursor.sequence,
                          actor=actor, action=action, resource=resource,
                          outcome=outcome)
    db.add(row)
    return row


def _rows(db: Session, project_id: str, after: int) -> list[dict]:
    items = db.scalars(select(ProjectActivity).where(
        ProjectActivity.project_id == project_id,
        ProjectActivity.sequence > after).order_by(
        ProjectActivity.sequence).limit(100)).all()
    return [{'sequence': row.sequence, 'actor': row.actor, 'action': row.action,
             'resource': row.resource, 'outcome': row.outcome,
             'created_at': row.created_at.isoformat()}
            for row in items]


@router.get('/api/projects/{project_id}/activity')
def list_project_activity(project_id: str, after: int = 0,
                          _: OwnerSession = Depends(current_session),
                          db: Session = Depends(db_session)):
    if after < 0:
        raise HTTPException(422, 'Invalid activity cursor')
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    return _rows(db, project_id, after)


@router.get('/api/projects/{project_id}/activity/stream')
async def stream_project_activity(project_id: str, request: Request,
                                  after: int = 0,
                                  last_event_id: str | None = Header(default=None)):
    with session_factory()() as db:
        current_session(request, db)
        if db.get(Project, project_id) is None:
            raise HTTPException(404, 'Project not found')
    if last_event_id is not None:
        try:
            after = int(last_event_id)
        except ValueError as exc:
            raise HTTPException(422, 'Invalid activity cursor') from exc
    if after < 0:
        raise HTTPException(422, 'Invalid activity cursor')

    async def events():
        cursor = after
        started = time.monotonic()
        heartbeat = started
        yield ': connected\n\n'
        while time.monotonic() - started < 30:
            if await request.is_disconnected():
                return
            with session_factory()() as read_db:
                batch = _rows(read_db, project_id, cursor)
            for row in batch:
                cursor = row['sequence']
                yield (f"id: {cursor}\nevent: activity\ndata: "
                       f"{json.dumps(row, separators=(',', ':'))}\n\n")
            current = time.monotonic()
            if current - heartbeat >= 10:
                heartbeat = current
                yield ': heartbeat\n\n'
            await asyncio.sleep(.5)

    return StreamingResponse(events(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})
