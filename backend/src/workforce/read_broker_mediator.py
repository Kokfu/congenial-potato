"""Database authority checks around an experimental broker; no worker route."""
from sqlalchemy import select

from .db import session_factory
from .local_read_experiment import ReadDenied
from .activity import record_activity
from .models import AuditEvent, ExternalReadObservation, ReadEffectAttempt
from .read_broker_contract import BrokerOutcomeUnknown, verify_ticket
from .read_broker_result import ticket_digest, verify_broker_reply
from .read_effect_experiment import _locked, _reason, _deny, _event
from .read_observations import store_observation
from .tool_approval import _digest, exact_payload


def _attempt(db, invocation_id, envelope, ticket):
    attempt = db.scalar(select(ReadEffectAttempt).where(
        ReadEffectAttempt.invocation_id == invocation_id).with_for_update())
    if (str(ticket.attempt_id) != invocation_id or attempt is None or
            attempt.broker_ticket_hash is None or
            attempt.broker_ticket_hash != ticket_digest(envelope)):
        raise ReadDenied('Issued broker ticket unavailable')
    return attempt


def _authority(db, invocation, source, root, approval, attempt):
    reason = _reason(db, invocation, source, root, approval)
    if reason is None and (attempt.approval_id != approval.id or
            attempt.payload_hash != _digest(exact_payload(invocation)) or
            attempt.agent_id != source.agent_id or attempt.root_id != source.root_id):
        reason = 'attempt_changed'
    return reason


def authorize_broker_fetch(envelope: str, *, key: bytes,
                            experiment_enabled: bool = False) -> None:
    if not experiment_enabled:
        raise ReadDenied('Broker mediator experiment is disabled')
    ticket = verify_ticket(envelope, key=key)
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, str(ticket.attempt_id))
        attempt = _attempt(db, invocation.id, envelope, ticket)
        if attempt.status != 'unknown':
            raise ReadDenied('Broker attempt is no longer open')
        if attempt.broker_permit_consumed:
            raise BrokerOutcomeUnknown('Broker admission already consumed; no repeat permit')
        ticket.current()
        reason = _authority(db, invocation, source, root, approval, attempt)
        if reason:
            _deny(db, invocation, approval, attempt, reason)
            db.commit()
            raise ReadDenied('Broker fetch authority unavailable')
        ticket.current()
        attempt.broker_permit_consumed = True
        db.add(AuditEvent(actor='broker-mediator-experiment', action='read.broker.admit',
            resource=invocation.id, outcome='unknown',
            detail={'ticket_hash': attempt.broker_ticket_hash}))
        record_activity(db, project_id=invocation.project_id, actor='broker-mediator-experiment',
            action='read.broker.admit', resource=invocation.id, outcome='unknown')
        db.commit()  # durable before permit; release locks before DNS/socket work


def accept_broker_reply(envelope: str, signed: str, *, key: bytes,
                         experiment_enabled: bool = False) -> str:
    if not experiment_enabled:
        raise ReadDenied('Broker mediator experiment is disabled')
    ticket = verify_ticket(envelope, key=key)
    result = verify_broker_reply(signed, envelope, key=key)
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, str(ticket.attempt_id))
        attempt = _attempt(db, invocation.id, envelope, ticket)
        ticket.current()  # verification may have waited behind the root lock
        if not attempt.broker_permit_consumed:
            raise ReadDenied('Broker admission is unconfirmed')
        if attempt.status == 'succeeded':
            # A replay can acknowledge the same immutable historical result,
            # but cannot replace it or create another observation/audit event.
            row = db.get(ExternalReadObservation, attempt.observation_id)
            if row is None or (row.source_url, row.retrieved_at, row.media_type, row.size,
                    row.digest, row.content, row.trust_origin) != (
                    result.url, result.retrieved_at, result.media_type, result.size,
                    result.sha256, result.text, result.trust_origin):
                raise ReadDenied('Broker result changed after success')
            return 'succeeded'
        if attempt.status != 'unknown':
            return attempt.status
        reason = _authority(db, invocation, source, root, approval, attempt)
        if reason:
            _deny(db, invocation, approval, attempt, reason)
        else:
            ticket.current()  # grant/budget locks can also have waited
            row = store_observation(db, project_id=invocation.project_id,
                agent_id=source.agent_id, invocation_key=f'read-effect:{invocation.id}',
                expected_url=ticket.url, result=result)
            attempt.observation_id = row.id
            attempt.status = 'succeeded'
            invocation.status = 'succeeded'
            _event(db, invocation, 'succeeded')
            ticket.current()  # an expired flush rolls the entire transaction back
        db.commit()
        return attempt.status
