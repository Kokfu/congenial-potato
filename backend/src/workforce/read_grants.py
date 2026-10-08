"""Owner-controlled exact HTTPS destinations; no network effect is registered here."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .activity import record_activity
from .db import db_session
from .models import Agent, AuditEvent, OwnerSession, Project, ReadDestinationGrant
from .network_policy import PublicReadGrant, canonical_public_host
from .local_read_experiment import ReadDenied
from .security import current_session, require_csrf
from .services import AccessDenied, authorize_agent_project

router = APIRouter()


class GrantInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: UUID
    agent_id: UUID
    host: str = Field(min_length=1, max_length=180)
    expires_at: datetime
    enabled: bool


def grant_metadata(row: ReadDestinationGrant) -> dict:
    return {'id': row.id, 'project_id': row.project_id, 'agent_id': row.agent_id,
            'scheme': 'https', 'host': row.host, 'port': 443,
            'expires_at': row.expires_at, 'enabled': row.enabled,
            'revision': row.revision}


def set_read_grant(db: Session, *, project_id: str, agent_id: str,
                   host: str, expires_at: datetime, enabled: bool,
                   owner_id: str) -> ReadDestinationGrant:
    host = canonical_public_host(host)
    if len(host) > 180:
        raise ReadDenied('Destination hostname exceeds policy resource limit')
    now = datetime.now(timezone.utc)
    if (expires_at.tzinfo is None or expires_at <= now or
            expires_at > now + timedelta(days=30)):
        raise ReadDenied('Destination grant expiry unavailable')
    # Lock the project so concurrent first writes cannot race the unique scope.
    if db.scalar(select(Project.id).where(Project.id == project_id).with_for_update()) is None:
        raise ReadDenied('Project unavailable')
    if db.get(Agent, agent_id) is None:
        raise ReadDenied('Agent unavailable')
    row = db.scalar(select(ReadDestinationGrant).where(
        ReadDestinationGrant.project_id == project_id,
        ReadDestinationGrant.agent_id == agent_id,
        ReadDestinationGrant.host == host).with_for_update())
    if row is None:
        row = ReadDestinationGrant(project_id=project_id, agent_id=agent_id,
                                   host=host, expires_at=expires_at,
                                   enabled=enabled, revision=1)
        db.add(row)
    else:
        row.expires_at = expires_at
        row.enabled = enabled
        row.revision += 1
    db.flush()
    db.add(AuditEvent(actor=owner_id, action='read.grant.set', resource=row.id,
                      outcome='allowed', detail={'project_id': project_id,
                      'agent_id': agent_id, 'host': host, 'enabled': enabled,
                      'revision': row.revision}))
    record_activity(db, project_id=project_id, actor=owner_id,
                    action='read.grant.set', resource=row.id,
                    outcome='enabled' if enabled else 'disabled')
    return row


def active_read_grant(db: Session, *, project_id: str, agent_id: str,
                      host: str) -> PublicReadGrant:
    host = canonical_public_host(host)
    try:
        authorize_agent_project(db, agent_id, project_id, 'project.execute')
    except AccessDenied as exc:
        raise ReadDenied('Destination grant unavailable') from exc
    row = db.scalar(select(ReadDestinationGrant).where(
        ReadDestinationGrant.project_id == project_id,
        ReadDestinationGrant.agent_id == agent_id,
        ReadDestinationGrant.host == host))
    if row is None or not row.enabled or row.expires_at <= datetime.now(timezone.utc):
        raise ReadDenied('Destination grant unavailable')
    return PublicReadGrant(project_id=project_id, agent_id=agent_id,
                           host=host, expires_at=row.expires_at)


@router.get('/api/read-destination-grants')
def list_read_grants(project_id: UUID,
                     _: OwnerSession = Depends(current_session),
                     db: Session = Depends(db_session)):
    if db.get(Project, str(project_id)) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(ReadDestinationGrant).where(
        ReadDestinationGrant.project_id == str(project_id))
        .order_by(ReadDestinationGrant.host, ReadDestinationGrant.agent_id)
        .limit(200)).all()
    return [grant_metadata(row) for row in rows]


@router.post('/api/read-destination-grants', status_code=201)
def upsert_read_grant(data: GrantInput,
                      session: OwnerSession = Depends(require_csrf),
                      db: Session = Depends(db_session)):
    try:
        row = set_read_grant(db, project_id=str(data.project_id),
                             agent_id=str(data.agent_id), host=data.host,
                             expires_at=data.expires_at, enabled=data.enabled,
                             owner_id=session.owner_id)
    except ReadDenied as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return grant_metadata(row)
