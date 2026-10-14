"""Database-bound broker issuance experiment, never product worker dispatch.

A fresh attempt returns a one-time in-memory capability. Persist only its hash:
a restarted caller cannot recover it and turn an unknown outcome into a new
broker dispatch. An already-issued ticket can never be reissued, even if the
broker response or the ticket itself was lost.
"""
import hashlib
import hmac
import secrets

from sqlalchemy import select

from .activity import record_activity
from .db import session_factory
from .local_read_experiment import ReadDenied, ReadRequest
from .models import AuditEvent, ReadEffectAttempt, now
from .network_policy import (PinnedDestination, canonical_public_url,
    prepare_public_destination, revalidate_public_destination)
from .read_broker_contract import (BrokerOutcomeUnknown, BrokerReadTicket,
                                   MAX_TICKET_LIFETIME, sign_ticket)
from .read_effect_experiment import _locked, _reason, _deny
from .read_grants import active_read_grant, active_read_grant_record
from .tool_approval import _digest, exact_payload


def _audit(db, invocation, action, outcome, detail=None):
    db.add(AuditEvent(actor='broker-issuer-experiment', action=action,
        resource=invocation.id, outcome=outcome, detail=detail or {}))
    record_activity(db, project_id=invocation.project_id, actor='broker-issuer-experiment',
                    action=action, resource=invocation.id, outcome=outcome)


def begin_broker_attempt(invocation_id: str, *, resolver,
                          experiment_enabled: bool = False) -> tuple[bytes, PinnedDestination]:
    if not experiment_enabled or resolver is None:
        raise ReadDenied('Broker issuer experiment is disabled or uninjected')
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        if db.get(ReadEffectAttempt, invocation_id) is not None:
            raise BrokerOutcomeUnknown('Read attempt already exists; no restart dispatch')
        reason = _reason(db, invocation, source, root, approval)
        if reason:
            invocation.status = 'invalidated'
            if approval is not None and approval.status == 'approved':
                approval.status = 'invalidated'
            _audit(db, invocation, 'read.broker.prepare', 'denied', {'reason': reason})
            db.commit()
            raise ReadDenied('Broker source authority unavailable')
        request = ReadRequest(agent_id=source.agent_id, **invocation.arguments)
        host, _ = canonical_public_url(request.url)
        grant = active_read_grant(db, project_id=request.project_id,
                                 agent_id=request.agent_id, host=host)
        prepared = prepare_public_destination(request, grant, resolver=resolver)
        capability = secrets.token_bytes(32)
        db.add(ReadEffectAttempt(invocation_id=invocation.id,
            approval_id=approval.id, payload_hash=_digest(exact_payload(invocation)),
            agent_id=source.agent_id, root_id=source.root_id, status='unknown',
            broker_capability_hash=hashlib.sha256(capability).hexdigest()))
        _audit(db, invocation, 'read.broker.prepare', 'unknown')
        db.commit()
        return capability, prepared


def issue_broker_ticket(invocation_id: str, *, capability: bytes,
                        prepared: PinnedDestination, key: bytes, resolver,
                        experiment_enabled: bool = False) -> str:
    if not experiment_enabled or resolver is None:
        raise ReadDenied('Broker issuer experiment is disabled or uninjected')
    if not isinstance(capability, bytes) or len(capability) != 32:
        raise ReadDenied('Broker attempt capability unavailable')
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        attempt = db.scalar(select(ReadEffectAttempt).where(
            ReadEffectAttempt.invocation_id == invocation_id).with_for_update())
        if (attempt is None or attempt.broker_capability_hash is None or
                not hmac.compare_digest(attempt.broker_capability_hash,
                                        hashlib.sha256(capability).hexdigest())):
            raise ReadDenied('Broker attempt capability unavailable')
        if attempt.broker_ticket_hash is not None:
            raise BrokerOutcomeUnknown('Broker ticket already issued; no reissue')
        if attempt.status != 'unknown':
            raise ReadDenied('Broker attempt is no longer open')
        reason = _reason(db, invocation, source, root, approval)
        if reason is None and (attempt.approval_id != approval.id or
                attempt.payload_hash != _digest(exact_payload(invocation)) or
                attempt.agent_id != source.agent_id or attempt.root_id != source.root_id):
            reason = 'attempt_changed'
        if reason:
            _deny(db, invocation, approval, attempt, reason)
            _audit(db, invocation, 'read.broker.issue', 'denied', {'reason': reason})
            db.commit()
            raise ReadDenied('Broker source authority unavailable')
        request = ReadRequest(agent_id=source.agent_id, **invocation.arguments)
        host, _ = canonical_public_url(request.url)
        grant = active_read_grant_record(db, project_id=request.project_id,
                                        agent_id=request.agent_id, host=host)
        public_grant = active_read_grant(db, project_id=request.project_id,
                                        agent_id=request.agent_id, host=host)
        revalidate_public_destination(request, public_grant, prepared, resolver=resolver)
        issued = now()
        ticket = BrokerReadTicket(attempt_id=invocation.id, approval_id=approval.id,
            project_id=invocation.project_id, agent_id=source.agent_id, root_id=source.root_id,
            payload_hash=attempt.payload_hash, policy_hash=_digest(invocation.policy_snapshot),
            schema_hash=invocation.schema_hash, grant_id=grant.id, grant_revision=grant.revision,
            grant_expires_at=grant.expires_at, issued_at=issued,
            expires_at=min(issued + MAX_TICKET_LIFETIME, grant.expires_at, approval.expires_at),
            url=request.url, max_bytes=request.max_bytes, timeout_seconds=request.timeout_seconds,
            addresses=prepared.addresses)
        envelope = sign_ticket(ticket, key=key)
        attempt.broker_ticket_hash = hashlib.sha256(envelope.encode()).hexdigest()
        attempt.broker_issued_at = issued
        _audit(db, invocation, 'read.broker.issue', 'unknown',
               {'approval_id': approval.id, 'ticket_hash': attempt.broker_ticket_hash})
        db.commit()
        return envelope
