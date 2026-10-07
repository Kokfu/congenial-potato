from decimal import Decimal

from dbos import DBOS
from sqlalchemy import select

from test_plans import setup_manager
from workforce.db import session_factory
from workforce.models import AuditEvent, BudgetAccount, Execution, Outbox, Task
from workforce.worker import dispatch_once


def run_child(execution_id):
    DBOS(config={'name': 'workforce-test',
                 'system_database_url': 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
                 'application_version': 'usage-normalization-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'succeeded'
    finally:
        DBOS.destroy()


def test_manager_and_specialist_delegation_share_root_and_deduplicate(authenticated):
    headers, project, specialist, outsider, root_id = setup_manager(authenticated)
    url = f'/api/executions/{root_id}/delegate'
    payload = {'request_key': 'child-a', 'work_key': 'child-a',
               'title': 'Child task', 'agent_id': specialist}
    denied = authenticated.post(url, json={**payload, 'agent_id': outsider}, headers=headers)
    assert denied.status_code == 403
    made = authenticated.post(url, json=payload, headers=headers)
    assert made.status_code == 202, made.text
    child_id = made.json()['id']
    assert made.json()['root_id'] == root_id and made.json()['depth'] == 1
    assert authenticated.post(url, json=payload, headers=headers).json()['id'] == child_id
    assert authenticated.post(url, json={**payload, 'title': 'Changed'}, headers=headers).status_code == 409
    assert authenticated.post(url, json={**payload, 'request_key': 'child-b'},
                              headers=headers).status_code == 409
    children = authenticated.get(f'/api/executions/{root_id}/children').json()
    assert len(children) == 1 and children[0]['id'] == child_id
    with session_factory()() as db:
        child = db.get(Execution, child_id)
        assert child.parent_id == root_id and child.root_id == root_id
        assert db.get(BudgetAccount, child_id) is None
        assert db.get(BudgetAccount, root_id).cap == Decimal('1.000000')
        assert db.get(Task, child.task_id).parent_id == db.get(Execution, root_id).task_id
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.action == 'execution.delegate', AuditEvent.resource == child_id)).all()) == 1
    run_child(child_id)
    with session_factory()() as db:
        manager_id = db.get(Execution, root_id).agent_id
    grandchild = authenticated.post(f'/api/executions/{child_id}/delegate', json={
        'request_key': 'grandchild-a', 'work_key': 'grandchild-a',
        'title': 'Specialist asks Manager', 'agent_id': manager_id}, headers=headers)
    assert grandchild.status_code == 202, grandchild.text
    assert grandchild.json()['root_id'] == root_id and grandchild.json()['depth'] == 2
    with session_factory()() as db:
        account = db.get(BudgetAccount, root_id)
        account.reserved = account.cap
        db.commit()
    assert authenticated.post(f'/api/executions/{child_id}/delegate', json={
        'request_key': 'grandchild-b', 'work_key': 'grandchild-b',
        'title': 'No remaining budget', 'agent_id': manager_id}, headers=headers).status_code == 409
    with session_factory()() as db:
        assert db.scalar(select(Outbox.id).where(
            Outbox.idempotency_key == f'execution:{grandchild.json()["id"]}')) is not None
        assert db.get(BudgetAccount, root_id).reserved == Decimal('1.000000')
        db.get(BudgetAccount, root_id).reserved = Decimal('0.000000')
        db.commit()
    run_child(grandchild.json()['id'])
    third = authenticated.post(f"/api/executions/{grandchild.json()['id']}/delegate", json={
        'request_key': 'third', 'work_key': 'third', 'title': 'Third depth',
        'agent_id': specialist}, headers=headers)
    assert third.status_code == 202 and third.json()['depth'] == 3
    run_child(third.json()['id'])
    assert authenticated.post(f"/api/executions/{third.json()['id']}/delegate", json={
        'request_key': 'too-deep', 'work_key': 'too-deep', 'title': 'Fourth depth',
        'agent_id': manager_id}, headers=headers).status_code == 409


def test_delegation_child_limit_and_source_revocation(authenticated):
    headers, project, specialist, _, root_id = setup_manager(authenticated)
    url = f'/api/executions/{root_id}/delegate'
    with session_factory()() as db:
        manager = db.get(Execution, root_id).agent_id
    assert authenticated.post(f'/api/agents/{manager}/grants', json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': False},
        headers=headers).status_code == 201
    assert authenticated.post(url, json={
        'request_key': 'revoked', 'work_key': 'revoked',
        'title': 'Revoked source', 'agent_id': specialist}, headers=headers).status_code == 403
    assert authenticated.post(f'/api/agents/{manager}/grants', json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=headers).status_code == 201
    for number in range(4):
        assert authenticated.post(url, json={
            'request_key': f'child-{number}', 'work_key': f'child-{number}',
            'title': f'Child {number}', 'agent_id': specialist},
            headers=headers).status_code == 202
    assert authenticated.post(url, json={
        'request_key': 'child-4', 'work_key': 'child-4',
        'title': 'Fifth child', 'agent_id': specialist}, headers=headers).status_code == 409
