from dbos import DBOS
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import AuditEvent, PlanProposal, Task, TaskAssignment, TaskDependency
from workforce.worker import dispatch_once


def setup_manager(authenticated):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Plan fixture'}, headers=headers).json()
    other = authenticated.post('/api/projects', json={'name': 'Other'}, headers=headers).json()
    def agent(name, role):
        response = authenticated.post('/api/agents', json={
            'name': name, 'role': role, 'instructions': 'Synthetic',
            'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers)
        assert response.status_code == 201
        return response.json()['id']
    manager = agent('Manager', 'Manager')
    specialist = agent('Specialist', 'specialist')
    outsider = agent('Outsider', 'specialist')
    for agent_id, project_id in ((manager, project['id']), (specialist, project['id']),
                                 (outsider, other['id'])):
        assert authenticated.post(f'/api/agents/{agent_id}/grants', json={
            'project_id': project_id, 'action': 'project.execute', 'allowed': True},
            headers=headers).status_code == 201
    task = authenticated.post('/api/tasks', json={
        'project_id': project['id'], 'title': 'Manager source'}, headers=headers).json()
    dispatched = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={
        'agent_id': manager, 'root_cap': '1.0'}, headers=headers)
    assert dispatched.status_code == 202
    execution_id = dispatched.json()['execution_id']
    DBOS(config={'name': 'workforce-test',
                 'system_database_url': 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
                 'application_version': 'usage-normalization-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'succeeded'
    finally:
        DBOS.destroy()
    return headers, project, specialist, outsider, execution_id


def plan(execution_id, assignee):
    return {'source_execution_id': execution_id, 'proposal_key': 'plan-a',
            'expected_revision': 1, 'tasks': [
                {'work_key': 'research', 'title': 'Research', 'assignee_id': assignee,
                 'depends_on': []},
                {'work_key': 'review', 'title': 'Review', 'assignee_id': assignee,
                 'depends_on': ['research']}]}


def test_manager_plan_admission_is_atomic_and_idempotent(authenticated):
    headers, project, specialist, _, execution_id = setup_manager(authenticated)
    url = f"/api/projects/{project['id']}/plan-proposals"
    body = plan(execution_id, specialist)
    proposed = authenticated.post(url, json=body, headers=headers)
    assert proposed.status_code == 201, proposed.text
    repeated = authenticated.post(url, json=body, headers=headers)
    assert repeated.status_code == 200 and repeated.json()['id'] == proposed.json()['id']
    proposal_id = proposed.json()['id']
    assert authenticated.get(url).json()[0]['source_execution_id'] == execution_id
    admission = f'/api/plan-proposals/{proposal_id}/admit'
    assert authenticated.post(admission, json={'payload_hash': '0' * 64}, headers=headers).status_code == 409
    accepted = authenticated.post(admission, json={
        'payload_hash': proposed.json()['payload_hash']}, headers=headers)
    assert accepted.status_code == 200 and accepted.json()['status'] == 'admitted'
    assert authenticated.post(admission, json={
        'payload_hash': proposed.json()['payload_hash']}, headers=headers).status_code == 200
    assert authenticated.get('/api/projects').json()[0]['plan_revision'] == 2
    with session_factory()() as db:
        tasks = db.scalars(select(Task).where(Task.project_id == project['id'],
                                              Task.work_key.is_not(None))).all()
        assert {row.work_key for row in tasks} == {'research', 'review'}
        assert len(db.scalars(select(TaskDependency).where(TaskDependency.project_id == project['id'])).all()) == 1
        assert len(db.scalars(select(TaskAssignment).where(
            TaskAssignment.task_id.in_([row.id for row in tasks]))).all()) == 2
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.action == 'plan.admit', AuditEvent.resource == proposal_id)).all()) == 1


def test_manager_plan_rejects_cycles_scope_and_stale_revision(authenticated):
    headers, project, specialist, outsider, execution_id = setup_manager(authenticated)
    url = f"/api/projects/{project['id']}/plan-proposals"
    body = plan(execution_id, specialist)
    assert authenticated.post(url, json={**body, 'tasks': [body['tasks'][0],
        {**body['tasks'][1], 'depends_on': ['research', 'research']}]},
        headers=headers).status_code == 409
    assert authenticated.post(url, json={**body, 'tasks': [
        {**body['tasks'][0], 'depends_on': ['review']}, body['tasks'][1]]},
        headers=headers).status_code == 409
    assert authenticated.post(url, json={**body, 'tasks': [
        {**body['tasks'][0], 'assignee_id': outsider}, body['tasks'][1]]},
        headers=headers).status_code == 403
    assert authenticated.post(url, json={**body, 'tasks': [body['tasks'][0],
        {**body['tasks'][1], 'work_key': 'research'}]}, headers=headers).status_code == 409
    assert authenticated.post(url, json={**body, 'source_execution_id': 'missing'},
                              headers=headers).status_code == 409
    proposed = authenticated.post(url, json=body, headers=headers)
    assert proposed.status_code == 201
    another = authenticated.post(url, json={**body, 'proposal_key': 'plan-b'}, headers=headers)
    assert another.status_code == 201
    admit_url = f"/api/plan-proposals/{proposed.json()['id']}/admit"
    assert authenticated.post(admit_url, json={
        'payload_hash': proposed.json()['payload_hash']}, headers=headers).status_code == 200
    assert authenticated.post(f"/api/plan-proposals/{another.json()['id']}/admit", json={
        'payload_hash': another.json()['payload_hash']}, headers=headers).status_code == 409
    assert authenticated.post(url, json={**body, 'proposal_key': 'plan-c',
                                         'expected_revision': 2}, headers=headers).status_code == 409
    with session_factory()() as db:
        assert len(db.scalars(select(PlanProposal).where(
            PlanProposal.project_id == project['id'])).all()) == 2
