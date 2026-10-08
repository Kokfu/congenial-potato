"""Project-scoped knowledge ledger; candidate promotion is a separate review step."""
from collections.abc import Sequence
import hashlib
import json
import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (ArtifactVersion, AuditEvent, Execution, MemoryConflict,
                     MemoryRecord, MemorySource, Project, Task, TaskMessage, now)
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


class MemoryReviewError(ValueError):
    pass


def candidate_hash(project_id: str, agent_id: str, source_execution_id: str | None,
                   kind: str, subject_key: str, content: str,
                   trust_origin: str, sources: Sequence[tuple[str, str]]) -> str:
    payload = {'kind': kind, 'subject_key': subject_key, 'content': content,
               'project_id': project_id, 'agent_id': agent_id,
               'source_execution_id': source_execution_id,
               'trust_origin': trust_origin, 'sources': sorted([list(s) for s in sources])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def record_state_hash(db: Session, row: MemoryRecord) -> str:
    sources = db.scalars(select(MemorySource).where(MemorySource.record_id == row.id)).all()
    payload = {'id': row.id, 'project_id': row.project_id, 'subject_key': row.subject_key,
               'content': row.content, 'trust_origin': row.trust_origin,
               'status': row.status, 'superseded_by_id': row.superseded_by_id,
               'sources': sorted([source.source_kind, source.source_id] for source in sources)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def supersede_record(db: Session, *, old_id: str, replacement_id: str,
                     expected_state_hash: str, owner_id: str) -> MemoryRecord:
    hint = db.get(MemoryRecord, old_id)
    if hint is None:
        raise MemoryReviewError('Record unavailable')
    db.execute(select(Project).where(Project.id == hint.project_id).with_for_update()).scalar_one()
    rows = db.scalars(select(MemoryRecord).where(
        MemoryRecord.id.in_([old_id, replacement_id])).order_by(MemoryRecord.id)
        .with_for_update().execution_options(populate_existing=True)).all()
    indexed = {row.id: row for row in rows}
    old, replacement = indexed.get(old_id), indexed.get(replacement_id)
    if old is None or replacement is None or old.id == replacement.id:
        raise MemoryReviewError('Replacement unavailable')
    if old.status != 'active' or replacement.status != 'active':
        raise MemoryReviewError('Both records must be active')
    if old.project_id != replacement.project_id or old.subject_key != replacement.subject_key:
        raise MemoryReviewError('Replacement scope or subject changed')
    if record_state_hash(db, old) != expected_state_hash:
        raise MemoryReviewError('Record changed')
    old.status = 'superseded'
    old.superseded_by_id = replacement.id
    db.add(AuditEvent(actor=owner_id, action='memory.supersede', resource=old.id,
                      outcome='allowed', detail={'replacement_id': replacement.id,
                                                 'old_state_hash': expected_state_hash}))
    return old


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
                  subject_key: str, content: str, trust_origin: str,
                  sources: Sequence[tuple[str, str]],
                  source_execution_id: str | None = None) -> MemoryRecord:
    """Append an unverified agent assertion; never assign human authority here."""
    authorize_agent_project(db, agent_id, project_id, 'project.execute')
    if kind not in KINDS or trust_origin not in {'external_claim', 'model_inference'}:
        raise ValueError('Invalid candidate type or trust origin')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', subject_key):
        raise ValueError('Invalid subject key')
    if not content.strip() or len(content) > 20000 or not 1 <= len(sources) <= 20:
        raise ValueError('Invalid candidate content or source count')
    if len(set(sources)) != len(sources):
        raise ValueError('Duplicate source')
    for source_kind, source_id in sources:
        if _source_project(db, source_kind, source_id) != project_id:
            raise AccessDenied('Source unavailable in project')
    row = MemoryRecord(project_id=project_id, kind=kind, subject_key=subject_key,
                       content=content, payload_hash=candidate_hash(
                           project_id, agent_id, source_execution_id,
                           kind, subject_key, content, trust_origin, sources),
                       trust_origin=trust_origin, creator_kind='agent',
                       creator_id=agent_id, source_execution_id=source_execution_id,
                       status='candidate')
    db.add(row)
    db.flush()
    db.add_all(MemorySource(record_id=row.id, source_kind=kind, source_id=source_id)
               for kind, source_id in sources)
    return row


def review_candidate(db: Session, *, record_id: str, expected_hash: str,
                     owner_id: str, approved: bool,
                     acknowledged_conflict_ids: Sequence[str]) -> MemoryRecord:
    hint = db.get(MemoryRecord, record_id)
    if hint and hint.source_execution_id:
        source = db.get(Execution, hint.source_execution_id)
        if source:
            db.execute(select(Execution).where(Execution.id == source.root_id)
                       .with_for_update()).scalar_one_or_none()
    row = db.execute(select(MemoryRecord).where(MemoryRecord.id == record_id)
                     .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if row is None:
        raise MemoryReviewError('Candidate unavailable')
    # Lock the project as the common serialization point for competing reviews.
    db.execute(select(Project).where(Project.id == row.project_id).with_for_update()).scalar_one()
    sources = db.scalars(select(MemorySource).where(MemorySource.record_id == row.id)).all()
    refs = [(s.source_kind, s.source_id) for s in sources]
    if row.payload_hash != expected_hash:
        raise MemoryReviewError('Candidate changed')
    if row.status == ('active' if approved else 'rejected'):
        return row
    if row.status != 'candidate':
        raise MemoryReviewError('Candidate already decided')
    if candidate_hash(row.project_id, row.creator_id, row.source_execution_id,
                      row.kind, row.subject_key, row.content, row.trust_origin, refs) != expected_hash:
        raise MemoryReviewError('Candidate changed')
    authorize_agent_project(db, row.creator_id, row.project_id, 'project.execute')
    if not refs or any(_source_project(db, kind, source_id) != row.project_id
                       for kind, source_id in refs):
        raise MemoryReviewError('Source unavailable')
    for kind, source_id in refs:
        if kind == 'execution':
            execution = db.get(Execution, source_id)
            if execution.cancelled or execution.status != 'succeeded':
                raise MemoryReviewError('Source unavailable')
    if approved:
        existing = db.scalars(select(MemoryRecord).where(
            MemoryRecord.project_id == row.project_id,
            MemoryRecord.subject_key == row.subject_key,
            MemoryRecord.status == 'active').order_by(MemoryRecord.id)).all()
        if set(acknowledged_conflict_ids) != {other.id for other in existing} or len(
                acknowledged_conflict_ids) != len(existing):
            raise MemoryReviewError('Existing claims require exact conflict acknowledgement')
        db.add_all(MemoryConflict(record_id=row.id, other_record_id=other.id,
                                  acknowledged_by_id=owner_id) for other in existing)
        if row.kind == 'decision':
            row.trust_origin = 'approved_decision'
        row.status = 'active'
    else:
        if acknowledged_conflict_ids:
            raise MemoryReviewError('Conflicts are irrelevant to rejection')
        row.status = 'rejected'
    row.reviewed_by_id = owner_id
    row.reviewed_at = now()
    db.add(AuditEvent(actor=owner_id, action='memory.review', resource=row.id,
                      outcome=row.status, detail={'source_ids': [id for _, id in refs],
                                                  'conflict_ids': list(acknowledged_conflict_ids)}))
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
