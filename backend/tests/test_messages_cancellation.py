from concurrent.futures import ThreadPoolExecutor

from dbos import DBOS
from sqlalchemy import select

from test_plans import setup_manager
from test_delegation import run_child
from workforce.artifacts import apply_approved_artifacts
from workforce.cancellation import cancel_subtree, invalidate_cancelled_approvals
from workforce.db import session_factory
from workforce.delegation import DelegationError, DelegationInput, delegate
from workforce.models import Approval, AuditEvent, Execution, ModelCall, Owner, Task, TaskMessage
from workforce.worker import dispatch_once


def test_cancel_root_stops_queued_children_and_invalidates_approval(authenticated):
    headers, project, specialist, _, root_id = setup_manager(authenticated)
    approval = authenticated.get('/api/approvals').json()[0]
    assert authenticated.post(f"/api/approvals/{approval['id']}/decision", json={
        'approved': True, 'payload_hash': approval['payload_hash']}, headers=headers).status_code == 200
    child_ids = []
    for index in range(2):
        response = authenticated.post(f'/api/executions/{root_id}/delegate', json={
            'request_key': f'cancel-{index}', 'work_key': f'cancel-{index}',
            'title': f'Queued child {index}', 'agent_id': specialist}, headers=headers)
        assert response.status_code == 202
        child_ids.append(response.json()['id'])
    cancelled = authenticated.post(f'/api/executions/{root_id}/cancel', headers=headers)
    assert cancelled.status_code == 200 and cancelled.json()['cancelled_count'] == 3
    assert authenticated.post(f'/api/executions/{root_id}/cancel', headers=headers).json()['cancelled_count'] == 0
    assert authenticated.get('/api/approvals').json() == []
    assert apply_approved_artifacts() == 0
    assert authenticated.post(f'/api/executions/{root_id}/delegate', json={
        'request_key': 'too-late', 'work_key': 'too-late',
        'title': 'After cancel', 'agent_id': specialist}, headers=headers).status_code == 409
    DBOS(config={'name': 'workforce-test',
                 'system_database_url': 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
                 'application_version': 'usage-normalization-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 2
        for child_id in child_ids:
            assert DBOS.retrieve_workflow(f'execution:{child_id}').get_result() == 'cancelled'
    finally:
        DBOS.destroy()
    with session_factory()() as db:
        assert db.get(Approval, approval['id']).status == 'invalidated'
        assert db.scalar(select(ModelCall.id).where(ModelCall.execution_id.in_(child_ids))) is None
        assert all(db.get(Execution, child_id).cancelled for child_id in child_ids)
        assert all(db.get(Task, db.get(Execution, child_id).task_id).status == 'cancelled'
                   for child_id in child_ids)
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.action == 'execution.cancel')).all()) == 3
        assert invalidate_cancelled_approvals(db) == 0


def test_sender_bound_messages_are_scoped_deduplicated_and_reply_bounded(authenticated):
    headers, project, specialist, outsider, root_id = setup_manager(authenticated)
    child = authenticated.post(f'/api/executions/{root_id}/delegate', json={
        'request_key': 'message-child', 'work_key': 'message-child',
        'title': 'Message target', 'agent_id': specialist}, headers=headers)
    assert child.status_code == 202
    child_id = child.json()['id']
    task_id = child.json()['task_id']
    run_child(child_id)
    with session_factory()() as db:
        manager_id = db.get(Execution, root_id).agent_id
    url = f'/api/tasks/{task_id}/messages'
    payload = {'sender_execution_id': root_id, 'recipient_agent_id': specialist,
               'correlation_key': 'question', 'content': 'Please review the synthetic result'}
    assert authenticated.post(url, json={**payload, 'recipient_agent_id': outsider},
                              headers=headers).status_code == 403
    first = authenticated.post(url, json=payload, headers=headers)
    assert first.status_code == 201
    first_id = first.json()['id']
    assert authenticated.post(url, json=payload, headers=headers).status_code == 200
    assert authenticated.post(url, json={**payload, 'content': 'Changed'}, headers=headers).status_code == 409
    previous = first_id
    for index in range(1, 4):
        source, recipient = ((child_id, manager_id) if index % 2 else (root_id, specialist))
        reply = authenticated.post(url, json={
            'sender_execution_id': source, 'recipient_agent_id': recipient,
            'correlation_key': f'reply-{index}', 'content': f'Reply {index}',
            'reply_to_id': previous}, headers=headers)
        assert reply.status_code == 201 and reply.json()['reply_depth'] == index
        previous = reply.json()['id']
    assert authenticated.post(url, json={
        'sender_execution_id': root_id, 'recipient_agent_id': specialist,
        'correlation_key': 'reply-4', 'content': 'Too deep',
        'reply_to_id': previous}, headers=headers).status_code == 409
    rows = authenticated.get(url).json()
    assert len(rows) == 4 and all(row['trust_origin'] == 'agent_message' for row in rows)
    with session_factory()() as db:
        assert len(db.scalars(select(TaskMessage).where(TaskMessage.task_id == task_id)).all()) == 4
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.action == 'task.message.send')).all()) == 4
    assert authenticated.post(f'/api/executions/{root_id}/cancel', headers=headers).status_code == 200
    assert authenticated.post(url, json={**payload, 'correlation_key': 'after-cancel'},
                              headers=headers).status_code == 409


def test_concurrent_delegation_and_root_cancel_leave_no_live_child(authenticated):
    _, _, specialist, _, root_id = setup_manager(authenticated)
    with session_factory()() as db:
        owner_id = db.scalar(select(Owner.id))
    data = DelegationInput(request_key='race-child', work_key='race-child',
                           title='Race child', agent_id=specialist)
    def admit():
        with session_factory()() as db:
            try:
                child, _ = delegate(db, root_id, data, owner_id)
                db.commit()
                return child.id
            except DelegationError:
                db.rollback()
                return None
    def cancel():
        with session_factory()() as db:
            _, changed = cancel_subtree(db, root_id, owner_id)
            db.commit()
            return changed
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_child = pool.submit(admit)
        future_cancel = pool.submit(cancel)
        child_id = future_child.result()
        assert future_cancel.result() >= 1
    with session_factory()() as db:
        children = db.scalars(select(Execution).where(Execution.parent_id == root_id)).all()
        assert len(children) == (1 if child_id else 0)
        assert all(child.cancelled for child in children)
