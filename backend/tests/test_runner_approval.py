import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import (Agent, Approval, BudgetAccount, Execution, PolicyRule,
                              RunnerProfileGrant, SyntheticToolEffect, ToolInvocation)
from workforce.tool_effects import apply_admitted_tools
from test_runner_proposals import ACTION, setup, record


def proposed(client, *, image_id=None):
    h, project, agent, execution_id, output, payload = setup(client, image_id=image_id)
    invocation_id = record(execution_id, output)
    with session_factory()() as db:
        db.get(Execution, execution_id).status = 'succeeded'
        db.commit()
    return h, project, agent, execution_id, invocation_id, payload


def stage(client, h, invocation_id):
    return client.post(f'/api/tool-invocations/{invocation_id}/stage-runner-approval', headers=h)


def decide(client, h, invocation_id, payload_hash, approved=True):
    return client.post(f'/api/tool-invocations/{invocation_id}/decision', json={
        'payload_hash': payload_hash, 'approved': approved}, headers=h)


def test_exact_staged_approval_replay_and_closed_dispatch(authenticated):
    h, project, agent, execution_id, invocation_id, payload = proposed(authenticated)
    assert stage(authenticated, {}, invocation_id).status_code == 403
    staged = stage(authenticated, h, invocation_id)
    assert staged.status_code == 200, staged.text
    assert stage(authenticated, h, invocation_id).json() == staged.json()
    with session_factory()() as db:
        invocation = db.get(ToolInvocation, invocation_id)
        approval = db.get(Approval, staged.json()['approval_id'])
        grant = db.scalar(select(RunnerProfileGrant))
        assert invocation.status == 'awaiting_approval'
        assert approval.payload['arguments'] == invocation.arguments
        assert approval.payload['runner_binding'] == invocation.policy_snapshot['runner_grant']
        assert approval.payload['runner_scope'] == {'execution_id': execution_id, 'agent_id': agent, 'root_id': execution_id}
        assert approval.expires_at <= grant.expires_at
        assert approval.target_version == f'{grant.id}:1'
    assert decide(authenticated, {}, invocation_id, staged.json()['payload_hash']).status_code == 403
    assert decide(authenticated, h, invocation_id, 'b'*64).status_code == 409
    accepted = decide(authenticated, h, invocation_id, staged.json()['payload_hash'])
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'approved_staged'
    assert decide(authenticated, h, invocation_id, staged.json()['payload_hash']).json() == accepted.json()
    assert apply_admitted_tools() == 0
    with session_factory()() as db:
        assert len(db.scalars(select(Approval)).all()) == 1
        assert db.scalar(select(SyntheticToolEffect)) is None
    assert authenticated.post(f'/api/executions/{execution_id}/cancel', headers=h).status_code == 200
    with session_factory()() as db:
        assert db.get(ToolInvocation, invocation_id).status == 'invalidated'
        assert db.get(Approval, staged.json()['approval_id']).status == 'invalidated'


def mutate(client, details, change):
    h, project, agent, execution_id, invocation_id, payload = details
    if change == 'grant_revision':
        response = client.post('/api/runner-profile-grants', json=payload | {
            'expected_revision': 1,
            'expires_at': (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()}, headers=h)
        assert response.status_code == 201
        return
    if change == 'project_grant':
        assert client.post(f'/api/agents/{agent}/grants', json={'project_id': project,
            'action': 'project.execute', 'allowed': False}, headers=h).status_code == 201
        return
    with session_factory()() as db:
        invocation = db.get(ToolInvocation, invocation_id)
        grant = db.scalar(select(RunnerProfileGrant))
        source = db.get(Execution, execution_id)
        if change == 'grant_expired':
            grant.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
        elif change == 'grant_revoked':
            grant.enabled = False
        elif change == 'image':
            grant.image_id = 'sha256:'+'b'*64
        elif change == 'code':
            grant.job_sha256 = 'b'*64
        elif change == 'agent':
            db.get(Agent, agent).status = 'paused'
        elif change == 'policy':
            rule = db.scalar(select(PolicyRule).where(PolicyRule.subject == f'agent:{agent}'))
            rule.effect = 'deny'
            rule.revision += 1
        elif change == 'budget':
            db.get(BudgetAccount, execution_id).cap = 0
        elif change == 'cancelled':
            source.cancelled = True
        elif change == 'root':
            source.root_id = str(uuid4())
        elif change == 'source':
            source.status = 'failed'
        elif change == 'arguments':
            invocation.arguments = invocation.arguments | {'input': {'text': 'changed'}}
        elif change == 'schema':
            invocation.schema_hash = 'b'*64
        elif change == 'scope':
            invocation.policy_snapshot = invocation.policy_snapshot | {'runner_scope': {
                'execution_id': execution_id, 'agent_id': str(uuid4()), 'root_id': execution_id}}
        elif change == 'legacy_scope':
            invocation.policy_snapshot = {k: v for k, v in invocation.policy_snapshot.items() if k != 'runner_scope'}
        elif change == 'approval_expired':
            db.scalar(select(Approval)).expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
        elif change == 'approval_payload':
            approval = db.scalar(select(Approval))
            approval.payload = approval.payload | {'runner_binding': {}}
        else:
            raise AssertionError(change)
        db.commit()


CHANGES = ['grant_revision', 'grant_expired', 'grant_revoked', 'image', 'code',
           'project_grant', 'agent', 'policy', 'budget', 'cancelled', 'root',
           'source', 'arguments', 'schema', 'scope', 'legacy_scope']


@pytest.mark.parametrize('change', CHANGES)
def test_staging_rechecks_exact_current_authority(authenticated, change):
    details = proposed(authenticated)
    h, _, _, _, invocation_id, _ = details
    mutate(authenticated, details, change)
    response = stage(authenticated, h, invocation_id)
    assert response.status_code == 409, response.text
    with session_factory()() as db:
        assert db.get(ToolInvocation, invocation_id).status == 'invalidated'
        assert db.scalar(select(Approval)) is None
    assert apply_admitted_tools() == 0


@pytest.mark.parametrize('change', CHANGES+['approval_expired', 'approval_payload'])
def test_decision_rechecks_exact_current_authority(authenticated, change):
    details = proposed(authenticated)
    h, _, _, _, invocation_id, _ = details
    staged = stage(authenticated, h, invocation_id)
    assert staged.status_code == 200, staged.text
    mutate(authenticated, details, change)
    response = decide(authenticated, h, invocation_id, staged.json()['payload_hash'])
    assert response.status_code == 409, response.text
    with session_factory()() as db:
        assert db.get(ToolInvocation, invocation_id).status == 'invalidated'
        assert db.get(Approval, staged.json()['approval_id']).status in ('invalidated', 'expired')
        assert db.scalar(select(SyntheticToolEffect)) is None


def test_repeated_staging_rechecks_pending_approval(authenticated):
    details = proposed(authenticated)
    h, _, _, _, invocation_id, _ = details
    assert stage(authenticated, h, invocation_id).status_code == 200
    mutate(authenticated, details, 'grant_revision')
    assert stage(authenticated, h, invocation_id).status_code == 409
    with session_factory()() as db:
        assert db.get(ToolInvocation, invocation_id).status == 'invalidated'
        assert db.scalar(select(Approval)).status == 'invalidated'


def test_owner_can_reject_without_activating_runner(authenticated):
    h, _, _, _, invocation_id, _ = proposed(authenticated)
    staged = stage(authenticated, h, invocation_id).json()
    response = decide(authenticated, h, invocation_id, staged['payload_hash'], approved=False)
    assert response.status_code == 200 and response.json()['status'] == 'rejected'
    assert decide(authenticated, h, invocation_id, staged['payload_hash'], approved=False).json() == response.json()
    assert apply_admitted_tools() == 0


def test_concurrent_staging_creates_one_exact_approval(authenticated):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from workforce.models import Owner
    from workforce.tool_approval import stage_runner_approval
    _, _, _, _, invocation_id, _ = proposed(authenticated)
    barrier = Barrier(2)
    def stage_once():
        with session_factory()() as db:
            owner_id = db.scalar(select(Owner.id))
            barrier.wait(timeout=10)
            _, approval, reason = stage_runner_approval(db, invocation_id=invocation_id, owner_id=owner_id)
            assert reason is None
            db.commit()
            return approval.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: stage_once(), range(2)))
    assert ids[0] == ids[1]
    with session_factory()() as db:
        assert len(db.scalars(select(Approval)).all()) == 1


def test_approval_cannot_expire_while_waiting_for_policy_lock(authenticated):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import time
    from sqlalchemy import text
    from workforce.models import Owner
    from workforce.tool_approval import review_tool
    h, _, _, _, invocation_id, _ = proposed(authenticated)
    staged = stage(authenticated, h, invocation_id).json()
    expires = datetime.now(timezone.utc)+timedelta(seconds=3)
    with session_factory()() as db:
        db.get(Approval, staged['approval_id']).expires_at = expires
        db.commit()
    ready = Event()
    pids = []
    def decide_once():
        with session_factory()() as db:
            owner_id = db.scalar(select(Owner.id))
            pids.append(db.scalar(text('select pg_backend_pid()')))
            ready.set()
            invocation, approval, reason = review_tool(db, invocation_id=invocation_id,
                expected_hash=staged['payload_hash'], approved=True, owner_id=owner_id)
            db.commit()
            return invocation.status, approval.status, reason
    with session_factory()() as holder, ThreadPoolExecutor(max_workers=1) as pool:
        holder.scalar(select(PolicyRule).order_by(PolicyRule.id).limit(1).with_for_update())
        future = pool.submit(decide_once)
        try:
            assert ready.wait(timeout=5)
            deadline = time.monotonic()+5
            with session_factory()() as observer:
                while True:
                    wait = observer.scalar(text('select wait_event_type from pg_stat_activity where pid=:pid'), {'pid': pids[0]})
                    observer.commit()  # fresh statistics snapshot
                    if wait == 'Lock':
                        break
                    assert time.monotonic() < deadline, 'decision did not wait on policy lock'
                    time.sleep(.01)
            # The initial expiry check has passed; decision is blocked inside
            # policy evaluation. Let actual wall time pass while it holds locks.
            assert datetime.now(timezone.utc) < expires
            Event().wait(max(0, (expires-datetime.now(timezone.utc)).total_seconds())+.05)
        finally:
            holder.commit()
        assert future.result(timeout=10) == ('invalidated', 'expired', 'expired')
