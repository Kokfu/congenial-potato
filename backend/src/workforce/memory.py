"""Project-scoped knowledge ledger; candidate promotion is a separate review step."""
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (ArtifactVersion, Execution, MemoryRecord, MemorySource,
                     Task, TaskMessage)
from .services import AccessDenied, authorize_agent_project

SOURCE_MODELS = {
    'task': Task,
    'execution': Execution,
    'message': TaskMessage,
    'artifact_version': ArtifactVersion,
    'memory_record': MemoryRecord,
}
KINDS = {'fact', 'decision', 'observation', 'claim'}
ORIGINS = {'human_instruction', 'approved_decision', 'observed_result',
           'external_claim', 'model_inference'}


def _source_project(db: Session, kind: str, source_id: str) -> str | None:
    model = SOURCE_MODELS.get(kind)
    if model is None:
        return None
    row = db.get(model, source_id)
    if row is None:
        return None
    if isinstance(row, Execution):
        task = db.get(Task, row.task_id)
        return task.project_id if task else None
    return row.project_id


def add_candidate(db: Session, *, project_id: str, agent_id: str, kind: str,
                  content: str, trust_origin: str,
                  sources: Sequence[tuple[str, str]]) -> MemoryRecord:
    """Append an unverified agent assertion; never assign human authority here."""
    authorize_agent_project(db, agent_id, project_id, 'project.execute')
    if kind not in KINDS or trust_origin not in {'external_claim', 'model_inference'}:
        raise ValueError('Invalid candidate type or trust origin')
    if not content.strip() or len(content) > 20000 or not 1 <= len(sources) <= 20:
        raise ValueError('Invalid candidate content or source count')
    if len(set(sources)) != len(sources):
        raise ValueError('Duplicate source')
    for source_kind, source_id in sources:
        if _source_project(db, source_kind, source_id) != project_id:
            raise AccessDenied('Source unavailable in project')
    row = MemoryRecord(project_id=project_id, kind=kind, content=content,
                       trust_origin=trust_origin, creator_kind='agent',
                       creator_id=agent_id, status='candidate')
    db.add(row)
    db.flush()
    db.add_all(MemorySource(record_id=row.id, source_kind=kind, source_id=source_id)
               for kind, source_id in sources)
    return row


def get_record(db: Session, *, project_id: str, agent_id: str,
               record_id: str) -> tuple[MemoryRecord, list[MemorySource]] | None:
    authorize_agent_project(db, agent_id, project_id, 'project.execute')
    row = db.scalar(select(MemoryRecord).where(MemoryRecord.id == record_id,
                                               MemoryRecord.project_id == project_id,
                                               MemoryRecord.status != 'tombstoned'))
    if row is None:
        return None
    sources = db.scalars(select(MemorySource).where(MemorySource.record_id == row.id)
                         .order_by(MemorySource.id)).all()
    return row, list(sources)


def list_records(db: Session, *, project_id: str, agent_id: str,
                 limit: int = 50) -> list[MemoryRecord]:
    authorize_agent_project(db, agent_id, project_id, 'project.execute')
    if not 1 <= limit <= 100:
        raise ValueError('Invalid memory page size')
    return list(db.scalars(select(MemoryRecord).where(
        MemoryRecord.project_id == project_id, MemoryRecord.status == 'active')
        .order_by(MemoryRecord.created_at.desc(), MemoryRecord.id.desc())
        .limit(limit)).all())
