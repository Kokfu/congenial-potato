"""Store external content as cited data, never as authority."""
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .activity import record_activity
from .db import db_session
from .local_read_experiment import ReadResult
from .models import (AuditEvent, ExternalReadObservation, OwnerSession,
                     Project)
from .security import current_session
from .services import authorize_agent_project

router = APIRouter()


class ObservationError(ValueError):
    pass


def store_observation(db: Session, *, project_id: str, agent_id: str,
                      invocation_key: str, expected_url: str,
                      result: ReadResult) -> ExternalReadObservation:
    authorize_agent_project(db, agent_id, project_id, 'project.execute')
    body = result.text.encode('utf-8')
    if (not invocation_key or len(invocation_key) > 160 or
            result.url != expected_url or result.trust_origin != 'external_claim' or
            result.media_type not in ('text/plain', 'text/html') or
            result.retrieved_at.tzinfo is None or
            result.size != len(body) or result.size > 65536 or
            result.sha256 != hashlib.sha256(body).hexdigest()):
        raise ObservationError('Read result provenance invalid')
    db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
               {'key': invocation_key})
    fingerprint = hashlib.sha256(json.dumps({
        'project_id': project_id, 'agent_id': agent_id,
        'url': result.url, 'retrieved_at': result.retrieved_at.isoformat(),
        'media_type': result.media_type, 'size': result.size,
        'digest': result.sha256, 'trust_origin': result.trust_origin},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    existing = db.scalar(select(ExternalReadObservation).where(
        ExternalReadObservation.invocation_key == invocation_key).with_for_update())
    if existing is not None:
        if existing.payload_hash != fingerprint or hashlib.sha256(
                existing.content.encode('utf-8')).hexdigest() != existing.digest:
            raise ObservationError('Read invocation changed')
        return existing
    row = ExternalReadObservation(project_id=project_id, agent_id=agent_id,
        invocation_key=invocation_key, source_url=result.url,
        retrieved_at=result.retrieved_at, media_type=result.media_type,
        size=result.size, digest=result.sha256, content=result.text,
        payload_hash=fingerprint, trust_origin='external_claim')
    db.add(row)
    db.flush()
    db.add(AuditEvent(actor=agent_id, action='read.observe', resource=row.id,
                      outcome='allowed', effect_key=f'read-observe:{invocation_key}',
                      detail={'project_id': project_id, 'digest': result.sha256,
                              'source_url': result.url}))
    record_activity(db, project_id=project_id, actor=agent_id,
                    action='read.observe', resource=row.id, outcome='allowed')
    return row


def metadata(row: ExternalReadObservation) -> dict:
    return {'id': row.id, 'project_id': row.project_id,
            'agent_id': row.agent_id, 'source_url': row.source_url,
            'retrieved_at': row.retrieved_at, 'media_type': row.media_type,
            'size': row.size, 'digest': row.digest,
            'trust_origin': row.trust_origin}


@router.get('/api/projects/{project_id}/read-observations')
def list_read_observations(project_id: str,
                           _: OwnerSession = Depends(current_session),
                           db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(ExternalReadObservation).where(
        ExternalReadObservation.project_id == project_id).order_by(
        ExternalReadObservation.retrieved_at.desc(),
        ExternalReadObservation.id).limit(100)).all()
    return [metadata(row) for row in rows]


@router.get('/api/projects/{project_id}/read-observations/{observation_id}')
def get_read_observation(project_id: str, observation_id: str,
                         _: OwnerSession = Depends(current_session),
                         db: Session = Depends(db_session)):
    row = db.get(ExternalReadObservation, observation_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(404, 'Read observation not found')
    return {**metadata(row), 'content': row.content}
