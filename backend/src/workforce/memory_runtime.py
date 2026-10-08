"""Strict synthetic memory output contract; source authority comes from execution."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .memory import add_candidate
from .models import AuditEvent, Execution, MemoryRecord, Task
from .services import AccessDenied


class MemoryOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['fact', 'decision', 'observation', 'claim']
    subject_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    content: str = Field(min_length=1, max_length=20000)
    trust_origin: Literal['external_claim', 'model_inference']


def parse_memory_output(content: str) -> MemoryOutput:
    if len(content.encode('utf-8')) > 16384:
        raise ValueError('Memory output too large')

    def distinct_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate key')
            result[key] = value
        return result

    try:
        raw = json.loads(content, object_pairs_hook=distinct_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid constant')))
        return MemoryOutput.model_validate(raw)
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValueError('Invalid memory output') from exc


def record_memory_output(db: Session, execution: Execution, content: str) -> MemoryRecord | None:
    if db.scalar(select(MemoryRecord.id).where(
        MemoryRecord.source_execution_id == execution.id)) is not None:
        return None
    try:
        output = parse_memory_output(content)
        project_id = db.get(Task, execution.task_id).project_id
        row = add_candidate(db, project_id=project_id, agent_id=execution.agent_id,
                            kind=output.kind, subject_key=output.subject_key,
                            content=output.content, trust_origin=output.trust_origin,
                            sources=[('execution', execution.id)],
                            source_execution_id=execution.id)
    except (ValueError, AccessDenied) as exc:
        db.add(AuditEvent(actor=execution.agent_id, action='memory.parse',
                          resource=execution.id, outcome='denied',
                          effect_key=f'memory.parse:{execution.id}',
                          detail={'reason': str(exc)}))
        return None
    db.add(AuditEvent(actor=execution.agent_id, action='memory.propose',
                      resource=row.id, outcome='pending',
                      detail={'source_execution_id': execution.id,
                              'payload_hash': row.payload_hash}))
    return row
