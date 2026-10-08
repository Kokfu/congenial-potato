"""Private owner review of project memory candidates."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .memory import MemoryReviewError, review_candidate
from .models import MemoryRecord, MemorySource, OwnerSession, Project
from .security import current_session, require_csrf
from .services import AccessDenied

router = APIRouter()


class ReviewInput(BaseModel):
    approved: bool
    payload_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    acknowledged_conflict_ids: list[str] = Field(default_factory=list, max_length=100)


@router.get('/api/memory-candidates')
def list_memory_candidates(project_id: str, _: OwnerSession = Depends(current_session),
                           db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(MemoryRecord).where(
        MemoryRecord.project_id == project_id, MemoryRecord.status == 'candidate')
        .order_by(MemoryRecord.created_at, MemoryRecord.id).limit(100)).all()
    result = []
    for row in rows:
        sources = db.scalars(select(MemorySource).where(MemorySource.record_id == row.id)).all()
        conflicts = db.scalars(select(MemoryRecord).where(
            MemoryRecord.project_id == project_id,
            MemoryRecord.subject_key == row.subject_key,
            MemoryRecord.status == 'active').order_by(MemoryRecord.id)).all()
        result.append({'id': row.id, 'kind': row.kind, 'subject_key': row.subject_key,
                       'content': row.content, 'trust_origin': row.trust_origin,
                       'payload_hash': row.payload_hash,
                       'sources': [{'kind': s.source_kind, 'id': s.source_id} for s in sources],
                       'existing_claims': [{'id': other.id, 'content': other.content,
                                            'trust_origin': other.trust_origin} for other in conflicts]})
    return result


@router.post('/api/memory-candidates/{record_id}/decision')
def decide_memory_candidate(record_id: str, data: ReviewInput,
                            session: OwnerSession = Depends(require_csrf),
                            db: Session = Depends(db_session)):
    try:
        row = review_candidate(db, record_id=record_id, expected_hash=data.payload_hash,
                               owner_id=session.owner_id, approved=data.approved,
                               acknowledged_conflict_ids=data.acknowledged_conflict_ids)
    except AccessDenied as exc:
        raise HTTPException(403, 'Project access denied') from exc
    except MemoryReviewError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return {'id': row.id, 'status': row.status, 'trust_origin': row.trust_origin}
