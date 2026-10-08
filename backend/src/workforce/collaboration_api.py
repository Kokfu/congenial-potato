"""Owner review for untrusted runtime collaboration proposals."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .collaboration import CollaborationError, decide_candidate
from .db import db_session
from .delegation import DelegationError
from .messages import MessageError
from .models import CollaborationProposal, OwnerSession, Project
from .plans import PlanError
from .security import current_session, require_csrf
from .services import AccessDenied

router = APIRouter()


class DecisionInput(BaseModel):
    approved: bool
    payload_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


@router.get('/api/collaboration-proposals')
def list_candidates(project_id: str, _: OwnerSession = Depends(current_session),
                    db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(CollaborationProposal).where(
        CollaborationProposal.project_id == project_id).order_by(
        CollaborationProposal.created_at, CollaborationProposal.id)).all()
    return [{'id': row.id, 'kind': row.kind, 'status': row.status,
             'source_execution_id': row.source_execution_id,
             'payload_hash': row.payload_hash, 'payload': row.payload,
             'admitted_ref': row.admitted_ref} for row in rows]


@router.post('/api/collaboration-proposals/{proposal_id}/decision')
def decide_collaboration(proposal_id: str, data: DecisionInput,
                         session: OwnerSession = Depends(require_csrf),
                         db: Session = Depends(db_session)):
    try:
        row = decide_candidate(db, proposal_id, data.payload_hash,
                               data.approved, session.owner_id)
    except AccessDenied as exc:
        raise HTTPException(403, 'Project access denied') from exc
    except (CollaborationError, DelegationError, MessageError, PlanError) as exc:
        raise HTTPException(404 if getattr(exc, 'code', None) == 'proposal_missing' else 409,
                            str(exc)) from exc
    db.commit()
    return {'id': row.id, 'status': row.status, 'admitted_ref': row.admitted_ref}
