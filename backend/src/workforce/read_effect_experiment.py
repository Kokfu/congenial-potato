"""Phase 7.4d proof only: injected DNS/transport, never worker dispatch.

A committed attempt fences the request. An interrupted attempt is unknown and
cannot be retried, even if no response was checkpointed. No real transport or
resolver is selected here; only the isolated test harness calls this service.
"""
from collections.abc import Callable

from sqlalchemy import select

from .activity import record_activity
from .db import session_factory
from .local_read_experiment import ReadDenied, ReadRequest
from .models import (Approval, AuditEvent, BudgetAccount, Execution,
                     ReadEffectAttempt, ToolInvocation)
from .network_policy import (canonical_public_url, execute_public_read_experiment,
                             prepare_public_destination)
from .read_grants import active_read_grant
from .read_observations import store_observation
from .tool_approval import _invalid_reason, _digest, exact_payload


def _locked(db, invocation_id):
    hint = db.get(ToolInvocation, invocation_id)
    if hint is None or hint.action != 'project.web.read':
        raise ReadDenied('Web read unavailable')
    source = db.get(Execution, hint.execution_id)
    if source is None:
        raise ReadDenied('Read source unavailable')
    root = db.scalar(select(Execution).where(Execution.id == source.root_id)
                     .with_for_update().execution_options(populate_existing=True))
    db.refresh(source)
    invocation = db.scalar(select(ToolInvocation).where(
        ToolInvocation.id == invocation_id).with_for_update()
        .execution_options(populate_existing=True))
    approval = db.scalar(select(Approval).where(
        Approval.tool_invocation_id == invocation_id).with_for_update()
        .execution_options(populate_existing=True))
    return invocation, source, root, approval


def _reason(db, invocation, source, root, approval):
    if root is None or root.cancelled:
        return 'root_unavailable'
    if invocation.status != 'approved_staged':
        return 'invocation_unavailable'
    if (invocation.policy_decision != 'require_approval' or approval is None or
            approval.status != 'approved' or
            approval.decision_payload_hash != approval.payload_hash):
        return 'approval_unavailable'
    reason = _invalid_reason(db, invocation, approval, source)
    if reason:
        return reason
    account = db.scalar(select(BudgetAccount).where(
        BudgetAccount.root_id == source.root_id).with_for_update())
    # This fixture has no monetary cost. It cannot authorize a paid read. An
    # exhausted/overrun root still denies it; no invented charge is recorded.
    if (account is None or account.currency != 'USD' or account.cap <= 0 or
            account.reserved < 0 or account.spent < 0 or
            account.cap - account.spent - account.reserved <= 0):
        return 'root_budget_unavailable'
    return None


def _event(db, invocation, outcome, reason=None):
    db.add(AuditEvent(actor='read-experiment', action='read.effect',
        resource=invocation.id, outcome=outcome,
        detail={'reason': reason} if reason else {}))
    record_activity(db, project_id=invocation.project_id, actor='read-experiment',
                    action='read.effect', resource=invocation.id, outcome=outcome)


def _deny(db, invocation, approval, attempt, reason):
    attempt.status = 'discarded'
    attempt.reason = reason
    invocation.status = 'invalidated'
    if approval is not None and approval.status == 'approved':
        approval.status = 'invalidated'
    _event(db, invocation, 'discarded', reason)


def run_read_effect_experiment(invocation_id: str, *, resolver,
                               connection_factory,
                               experiment_enabled: bool = False,
                               after_attempt_commit: Callable | None = None,
                               after_fetch: Callable | None = None) -> str:
    """One request at most; return its durable state on duplicates/restarts.

    Hooks simulate process loss or committed authority changes in tests. A crash
    (including after fetch) leaves `unknown`, deliberately without page content.
    """
    if not experiment_enabled or resolver is None or connection_factory is None:
        raise ReadDenied('Mediated read experiment is disabled or uninjected')
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        existing = db.get(ReadEffectAttempt, invocation_id)
        if existing is not None:
            return existing.status
        reason = _reason(db, invocation, source, root, approval)
        if reason:
            invocation.status = 'invalidated'
            if approval is not None and approval.status == 'approved':
                approval.status = 'invalidated'
            _event(db, invocation, 'denied', reason)
            db.commit()
            return 'denied'
        request = ReadRequest(agent_id=source.agent_id, **invocation.arguments)
        host, _ = canonical_public_url(request.url)
        grant = active_read_grant(db, project_id=request.project_id,
                                 agent_id=request.agent_id, host=host)
        prepared = prepare_public_destination(request, grant, resolver=resolver)
        attempt = ReadEffectAttempt(invocation_id=invocation_id,
            approval_id=approval.id, payload_hash=_digest(exact_payload(invocation)),
            agent_id=source.agent_id, root_id=source.root_id, status='unknown')
        db.add(attempt)
        _event(db, invocation, 'attempted')
        db.commit()  # durable before any request; unknown is never auto-retried
    if after_attempt_commit:
        after_attempt_commit()
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        attempt = db.get(ReadEffectAttempt, invocation_id)
        reason = _reason(db, invocation, source, root, approval)
        if reason is None and (attempt.approval_id != approval.id or
                attempt.payload_hash != _digest(exact_payload(invocation)) or
                attempt.agent_id != source.agent_id or attempt.root_id != source.root_id):
            reason = 'attempt_changed'
        if reason:
            _deny(db, invocation, approval, attempt, reason)
            db.commit()
            return attempt.status
        # Refresh expiry as well as grant revision before the second DNS check.
        grant = active_read_grant(db, project_id=request.project_id,
                                 agent_id=request.agent_id, host=host)
        db.commit()
    try:
        result = execute_public_read_experiment(request, grant, prepared,
            experiment_enabled=True, resolver=resolver,
            connection_factory=connection_factory)
    except Exception:
        # A transport error may occur after the request was sent. Preserve the
        # unknown outcome instead of assuming the remote side saw nothing.
        with session_factory()() as db:
            invocation, _, _, _ = _locked(db, invocation_id)
            attempt = db.get(ReadEffectAttempt, invocation_id)
            attempt.reason = 'fetch_unconfirmed'
            _event(db, invocation, 'unknown', 'fetch_unconfirmed')
            db.commit()
        raise
    if after_fetch:
        after_fetch()
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        attempt = db.get(ReadEffectAttempt, invocation_id)
        reason = _reason(db, invocation, source, root, approval)
        if reason is None and (attempt.approval_id != approval.id or
                attempt.payload_hash != _digest(exact_payload(invocation)) or
                attempt.agent_id != source.agent_id or attempt.root_id != source.root_id):
            reason = 'attempt_changed'
        if reason:
            _deny(db, invocation, approval, attempt, reason)
        else:
            observation = store_observation(db, project_id=invocation.project_id,
                agent_id=source.agent_id, invocation_key=f'read-effect:{invocation.id}',
                expected_url=request.url, result=result)
            attempt.observation_id = observation.id
            attempt.status = 'succeeded'
            invocation.status = 'succeeded'
            _event(db, invocation, 'succeeded')
        db.commit()
        return attempt.status
