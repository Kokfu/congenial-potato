"""Parse untrusted model output and admit only reviewed, exact proposals."""
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .delegation import DelegationInput, delegate
from .messages import MessageInput, send_message
from .models import AuditEvent, CollaborationProposal, Execution, Task
from .plans import PlanInput, PlanTask, admit, propose
from .activity import record_activity

MAX_PROPOSAL_BYTES = 16384


class PlanCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['plan']
    proposal_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    expected_revision: int = Field(ge=1)
    tasks: list[PlanTask] = Field(min_length=1, max_length=12)


class DelegationCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['delegation']
    request_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    work_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    title: str = Field(min_length=1, max_length=240)
    agent_id: str


class MessageCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['message']
    task_id: str
    recipient_agent_id: str
    correlation_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    content: str = Field(min_length=1, max_length=10000)
    reply_to_id: str | None = None


CANDIDATES = {'plan': PlanCandidate, 'delegation': DelegationCandidate,
              'message': MessageCandidate}


class CollaborationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def proposal_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def parse_candidate(content: str) -> dict:
    if len(content.encode('utf-8')) > MAX_PROPOSAL_BYTES:
        raise CollaborationError('proposal_too_large')
    try:
        def distinct_pairs(pairs: list[tuple[str, object]]) -> dict:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON key')
                result[key] = value
            return result
        def reject_constant(_: str) -> None:
            raise ValueError('Invalid JSON constant')
        raw = json.loads(content, object_pairs_hook=distinct_pairs,
                         parse_constant=reject_constant)
        if not isinstance(raw, dict) or raw.get('kind') not in CANDIDATES:
            raise CollaborationError('invalid_contract')
        return CANDIDATES[raw['kind']].model_validate(raw).model_dump(mode='json')
    except (ValueError, TypeError, ValidationError) as exc:
        raise CollaborationError('invalid_contract') from exc


def record_candidate(db: Session, execution: Execution,
                     content: str) -> CollaborationProposal | None:
    if db.scalar(select(CollaborationProposal.id).where(
        CollaborationProposal.source_execution_id == execution.id)) is not None:
        return None
    project_id = db.get(Task, execution.task_id).project_id
    try:
        payload = parse_candidate(content)
    except CollaborationError as exc:
        db.add(AuditEvent(actor=execution.agent_id, action='collaboration.parse',
                          resource=execution.id, outcome='denied',
                          effect_key=f'collaboration.parse:{execution.id}',
                          detail={'reason': exc.code}))
        record_activity(db, project_id=project_id, actor=execution.agent_id,
                        action='collaboration.parse', resource=execution.id,
                        outcome='denied')
        return None
    row = CollaborationProposal(source_execution_id=execution.id,
                                project_id=project_id, kind=payload['kind'],
                                payload=payload, payload_hash=proposal_hash(payload),
                                status='pending')
    db.add(row)
    db.flush()
    db.add(AuditEvent(actor=execution.agent_id, action='collaboration.propose',
                      resource=row.id, outcome='pending',
                      detail={'kind': row.kind, 'payload_hash': row.payload_hash,
                              'source_execution_id': execution.id}))
    record_activity(db, project_id=project_id, actor=execution.agent_id,
                    action='collaboration.propose', resource=row.id,
                    outcome='pending')
    return row


def decide_candidate(db: Session, proposal_id: str, expected_hash: str,
                     approved: bool, owner_id: str) -> CollaborationProposal:
    row = db.execute(select(CollaborationProposal).where(
        CollaborationProposal.id == proposal_id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one_or_none()
    if row is None:
        raise CollaborationError('proposal_missing')
    if row.payload_hash != expected_hash or proposal_hash(row.payload) != expected_hash:
        raise CollaborationError('proposal_changed')
    if row.status == ('admitted' if approved else 'rejected'):
        return row
    if row.status != 'pending':
        raise CollaborationError('proposal_already_decided')
    execution = db.get(Execution, row.source_execution_id)
    if execution.cancelled or execution.status != 'succeeded':
        raise CollaborationError('source_unavailable')
    try:
        payload = CANDIDATES[row.kind].model_validate(row.payload)
    except (KeyError, ValidationError) as exc:
        raise CollaborationError('invalid_contract') from exc
    if not approved:
        row.status = 'rejected'
    elif isinstance(payload, PlanCandidate):
        data = PlanInput(source_execution_id=execution.id,
                         proposal_key=payload.proposal_key,
                         expected_revision=payload.expected_revision,
                         tasks=payload.tasks)
        plan, _ = propose(db, row.project_id, data, owner_id)
        admitted = admit(db, plan.id, plan.payload_hash, owner_id)
        row.admitted_ref = admitted.id
        row.status = 'admitted'
    elif isinstance(payload, DelegationCandidate):
        child, _ = delegate(db, execution.id, DelegationInput(
            request_key=payload.request_key, work_key=payload.work_key,
            title=payload.title, agent_id=payload.agent_id), owner_id)
        row.admitted_ref = child.id
        row.status = 'admitted'
    else:
        message, _ = send_message(db, payload.task_id, MessageInput(
            sender_execution_id=execution.id,
            recipient_agent_id=payload.recipient_agent_id,
            correlation_key=payload.correlation_key,
            content=payload.content, reply_to_id=payload.reply_to_id), owner_id)
        row.admitted_ref = message.id
        row.status = 'admitted'
    db.add(AuditEvent(actor=owner_id, action='collaboration.decision',
                      resource=row.id, outcome=row.status,
                      detail={'kind': row.kind, 'payload_hash': row.payload_hash,
                              'admitted_ref': row.admitted_ref}))
    record_activity(db, project_id=row.project_id, actor=owner_id,
                    action='collaboration.decision', resource=row.id,
                    outcome=row.status)
    return row
