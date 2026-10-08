"""Private owner review of project memory candidates."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .memory import MemoryReviewError, review_candidate
from .memory_search import search_project_records
from .memory_context import SummaryError, create_summary
from .models import (MemoryRecord, MemorySource, OwnerSession, Project,
                     ProjectSummaryCitation, ProjectSummaryVersion)
from .security import current_session, require_csrf
from .services import AccessDenied

router = APIRouter()


class SummaryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=3000)
    citation_ids: list[str] = Field(min_length=1, max_length=20)


@router.get('/api/projects/{project_id}/summaries')
def list_summaries(project_id: str, _: OwnerSession = Depends(current_session),
                   db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(ProjectSummaryVersion).where(
        ProjectSummaryVersion.project_id == project_id)
        .order_by(ProjectSummaryVersion.version.desc()).limit(30)).all()
    return [{'id': row.id, 'version': row.version, 'parent_id': row.parent_id,
             'content': row.content, 'digest': row.digest, 'author_id': row.author_id,
             'citation_ids': db.scalars(select(ProjectSummaryCitation.record_id).where(
                 ProjectSummaryCitation.summary_id == row.id)).all()}
            for row in rows]


@router.post('/api/projects/{project_id}/summaries', status_code=201)
def post_summary(project_id: str, data: SummaryInput,
                 session: OwnerSession = Depends(require_csrf),
                 db: Session = Depends(db_session)):
    try:
        row = create_summary(db, project_id=project_id, owner_id=session.owner_id,
                             expected_version=data.expected_version, content=data.content,
                             citation_ids=data.citation_ids)
    except SummaryError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return {'id': row.id, 'version': row.version, 'parent_id': row.parent_id,
            'digest': row.digest}


@router.get('/api/memory/search')
def search_memory(project_id: str, query: str, limit: int = 20,
                  _: OwnerSession = Depends(current_session),
                  db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    try:
        hits = search_project_records(db, project_id=project_id, query=query, limit=limit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return [hit.__dict__ for hit in hits]


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
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
