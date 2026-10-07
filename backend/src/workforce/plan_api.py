"""Owner-reviewed synthetic Manager plan proposals."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .models import OwnerSession, PlanProposal, Project
from .plans import PlanError, PlanInput, admit, propose
from .security import current_session, require_csrf
from .services import AccessDenied

router = APIRouter()


class AdmissionInput(BaseModel):
    payload_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


@router.get('/api/projects/{project_id}/plan-proposals')
def list_proposals(project_id: str, _: OwnerSession = Depends(current_session),
                   db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(PlanProposal).where(PlanProposal.project_id == project_id)
                      .order_by(PlanProposal.created_at, PlanProposal.id)).all()
    return [{'id': row.id, 'status': row.status, 'payload_hash': row.payload_hash,
             'payload': row.payload, 'source_execution_id': row.source_execution_id}
            for row in rows]


@router.post('/api/projects/{project_id}/plan-proposals', status_code=201)
def create_proposal(project_id: str, data: PlanInput, response: Response,
                    session: OwnerSession = Depends(require_csrf),
                    db: Session = Depends(db_session)):
    try:
        row, created = propose(db, project_id, data, session.owner_id)
    except AccessDenied as exc:
        raise HTTPException(403, 'Project access denied') from exc
    except PlanError as exc:
        raise HTTPException(404 if exc.code == 'project_missing' else 409, exc.code) from exc
    if not created:
        response.status_code = 200
    db.commit()
    return {'id': row.id, 'status': row.status, 'payload_hash': row.payload_hash}


@router.post('/api/plan-proposals/{proposal_id}/admit')
def admit_proposal(proposal_id: str, data: AdmissionInput,
                   session: OwnerSession = Depends(require_csrf),
                   db: Session = Depends(db_session)):
    try:
        row = admit(db, proposal_id, data.payload_hash, session.owner_id)
    except AccessDenied as exc:
        raise HTTPException(403, 'Project access denied') from exc
    except PlanError as exc:
        raise HTTPException(404 if exc.code == 'proposal_missing' else 409, exc.code) from exc
    db.commit()
    return {'id': row.id, 'status': row.status}
