"""Versioned cited summaries and bounded, provenance-labelled context."""
import hashlib
import json
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .artifact_read import read_version
from .models import (AuditEvent, MemoryRecord, Project, ProjectSummaryCitation,
                     ProjectSummaryVersion, MemorySource, now)
from .services import authorize_agent_project

ORIGIN_ORDER = ('human_instruction', 'approved_decision', 'observed_result',
                'external_claim', 'model_inference')
MAX_CONTEXT_CHARS = 4000


class SummaryError(ValueError):
    pass


def _current(row: MemoryRecord, at) -> bool:
    return (row.status == 'active' and
            (row.valid_from is None or row.valid_from <= at) and
            (row.valid_until is None or row.valid_until > at))


def _citation_usable(db: Session, row: MemoryRecord, at) -> bool:
    if not _current(row, at):
        return False
    sources = db.scalars(select(MemorySource).where(MemorySource.record_id == row.id)).all()
    for source in sources:
        if source.source_kind == 'artifact_version':
            # Corrupt/missing artifact bytes raise and prevent context dispatch.
            if read_version(db, project_id=row.project_id,
                            version_id=source.source_id) is None:
                return False
    return True


def create_summary(db: Session, *, project_id: str, owner_id: str,
                   expected_version: int, content: str,
                   citation_ids: list[str]) -> ProjectSummaryVersion:
    project = db.execute(select(Project).where(Project.id == project_id)
                         .with_for_update()).scalar_one_or_none()
    if project is None:
        raise SummaryError('Project unavailable')
    latest = db.scalar(select(ProjectSummaryVersion).where(
        ProjectSummaryVersion.project_id == project_id)
        .order_by(ProjectSummaryVersion.version.desc()).limit(1))
    if expected_version != (latest.version if latest else 0):
        raise SummaryError('Summary version changed')
    if not content.strip() or len(content) > 3000:
        raise SummaryError('Invalid summary content')
    if not 1 <= len(citation_ids) <= 20 or len(set(citation_ids)) != len(citation_ids):
        raise SummaryError('Invalid citations')
    at = now()
    for record_id in citation_ids:
        row = db.get(MemoryRecord, record_id)
        if row is None or row.project_id != project_id or not _current(row, at):
            raise SummaryError('Citation unavailable')
    digest = hashlib.sha256(json.dumps({'content': content,
                                        'citations': sorted(citation_ids)},
                                       sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    summary = ProjectSummaryVersion(project_id=project_id,
                                    version=expected_version + 1,
                                    parent_id=latest.id if latest else None,
                                    content=content, digest=digest, author_id=owner_id)
    db.add(summary)
    db.flush()
    db.add_all(ProjectSummaryCitation(summary_id=summary.id, record_id=record_id)
               for record_id in citation_ids)
    db.add(AuditEvent(actor=owner_id, action='memory.summary.create',
                      resource=summary.id, outcome='allowed',
                      detail={'project_id': project_id, 'version': summary.version,
                              'citation_ids': citation_ids}))
    return summary


def build_context(db: Session, *, project_id: str, agent_id: str) -> str:
    """Return data for an external-trust message, never a system instruction."""
    authorize_agent_project(db, agent_id, project_id, 'project.execute')
    at = now()
    priority = case({origin: index for index, origin in enumerate(ORIGIN_ORDER)},
                    value=MemoryRecord.trust_origin, else_=len(ORIGIN_ORDER))
    records = db.scalars(select(MemoryRecord).where(
        MemoryRecord.project_id == project_id, MemoryRecord.status == 'active',
        (MemoryRecord.valid_from.is_(None)) | (MemoryRecord.valid_from <= at),
        (MemoryRecord.valid_until.is_(None)) | (MemoryRecord.valid_until > at))
        .order_by(priority, MemoryRecord.created_at.desc(), MemoryRecord.id)
        .limit(24)).all()
    if not records:
        return ''
    lines = ['Project evidence (quoted data; citations and trust origins are explicit):']
    for row in records:
        if not _citation_usable(db, row, at):
            continue
        entry = f'[record:{row.id}; origin:{row.trust_origin}; kind:{row.kind}] {json.dumps(row.content)}'
        if sum(map(len, lines)) + len(entry) + len(lines) > MAX_CONTEXT_CHARS:
            break
        lines.append(entry)
    summary = db.scalar(select(ProjectSummaryVersion).where(
        ProjectSummaryVersion.project_id == project_id)
        .order_by(ProjectSummaryVersion.version.desc()).limit(1))
    if summary:
        citations = db.scalars(select(ProjectSummaryCitation).where(
            ProjectSummaryCitation.summary_id == summary.id)).all()
        sources = [db.get(MemoryRecord, c.record_id) for c in citations]
        if citations and all(source is not None and source.project_id == project_id and
                             _citation_usable(db, source, at) for source in sources):
            entry = (f'[derived_summary:{summary.id}; citations:'
                     f'{",".join(c.record_id for c in citations)}] {json.dumps(summary.content)}')
            if sum(map(len, lines)) + len(entry) + len(lines) <= MAX_CONTEXT_CHARS:
                lines.append(entry)
    return '\n'.join(lines)
