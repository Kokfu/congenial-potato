"""Bounded PostgreSQL lexical retrieval over authorized, current project memory."""
from dataclasses import dataclass
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import MemoryRecord, now
from .memory_context import _citation_usable
from .services import authorize_agent_project


@dataclass(frozen=True)
class SearchHit:
    record_id: str
    project_id: str
    subject_key: str
    kind: str
    trust_origin: str
    snippet: str
    rank: float


def _snippet(content: str, query: str) -> str:
    # Build snippets only from rows returned by the scoped SQL query.
    terms = re.findall(r'[\w]+', query.lower())
    lower = content.lower()
    positions = [lower.find(term) for term in terms if len(term) > 2]
    first = min((position for position in positions if position >= 0), default=0)
    start = max(0, first - 60)
    text = content[start:start + 240]
    return ('…' if start else '') + text + ('…' if start + 240 < len(content) else '')


def search_records(db: Session, *, project_id: str, agent_id: str,
                   query: str, limit: int = 20) -> list[SearchHit]:
    authorize_agent_project(db, agent_id, project_id, 'project.execute')
    return search_project_records(db, project_id=project_id, query=query, limit=limit)


def search_project_records(db: Session, *, project_id: str,
                           query: str, limit: int = 20) -> list[SearchHit]:
    """Caller must already be the authenticated owner or authorized agent."""
    if not query.strip() or len(query) > 200 or not 1 <= limit <= 50:
        raise ValueError('Invalid memory search bounds')
    vector = MemoryRecord.search_vector
    parsed = func.websearch_to_tsquery('english', query)
    rank = func.ts_rank_cd(vector, parsed).label('rank')
    current = now()
    rows = db.execute(select(MemoryRecord, rank).where(
        MemoryRecord.project_id == project_id,
        MemoryRecord.status == 'active',
        (MemoryRecord.valid_from.is_(None)) | (MemoryRecord.valid_from <= current),
        (MemoryRecord.valid_until.is_(None)) | (MemoryRecord.valid_until > current),
        vector.op('@@')(parsed))
        .order_by(rank.desc(), MemoryRecord.id).limit(limit)).all()
    return [SearchHit(record_id=row.id, project_id=row.project_id,
                      subject_key=row.subject_key, kind=row.kind,
                      trust_origin=row.trust_origin, snippet=_snippet(row.content, query),
                      rank=float(score)) for row, score in rows if _citation_usable(db, row, current)]
