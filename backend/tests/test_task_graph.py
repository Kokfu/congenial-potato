from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import AuditEvent, Execution, Project, Task, TaskDependency
from workforce.task_graph import TaskGraphError, add_dependency


def test_owner_dependency_api_rejects_cycles_scope_and_late_edges(authenticated):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Graph project'}, headers=headers).json()
    other = authenticated.post('/api/projects', json={'name': 'Other project'}, headers=headers).json()
    def task(name, project_id=project['id']):
        response = authenticated.post('/api/tasks', json={
            'project_id': project_id, 'title': name}, headers=headers)
        assert response.status_code == 201
        return response.json()['id']
    first, second, third = task('First'), task('Second'), task('Third')
    foreign = task('Foreign', other['id'])

    def link(dependent, prerequisite):
        return authenticated.post(f'/api/tasks/{dependent}/dependencies', json={
            'prerequisite_task_id': prerequisite}, headers=headers)

    created = link(second, first)
    assert created.status_code == 201
    duplicate = link(second, first)
    assert duplicate.status_code == 200 and duplicate.json()['id'] == created.json()['id']
    assert link(third, second).status_code == 201
    assert link(first, third).status_code == 409
    assert link(first, first).status_code == 409
    assert link(first, foreign).status_code == 404
    assert authenticated.get(f'/api/tasks/{second}/dependencies').json() == [
        {'id': created.json()['id'], 'prerequisite_task_id': first}]

    agent = authenticated.post('/api/agents', json={
        'name': 'Graph specialist', 'role': 'specialist', 'instructions': 'Synthetic',
        'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers).json()
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=headers).status_code == 201
    dispatch = f'/api/tasks/{second}/dispatch'
    body = {'agent_id': agent['id'], 'root_cap': '1.0'}
    assert authenticated.post(dispatch, json=body, headers=headers).status_code == 409
    with session_factory()() as db:
        assert db.scalar(select(Execution.id).where(Execution.task_id == second)) is None
        db.get(Task, first).status = 'completed'  # human acceptance API follows in a later slice
        db.commit()
    assert authenticated.post(dispatch, json=body, headers=headers).status_code == 202
    assert link(second, third).status_code == 409
    with session_factory()() as db:
        assert len(db.scalars(select(TaskDependency)).all()) == 2
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.action == 'task.dependency.add')).all()) == 2


def test_concurrent_opposite_edges_cannot_form_cycle():
    with session_factory()() as db:
        project = Project(name='Concurrent graph')
        db.add(project)
        db.flush()
        first = Task(project_id=project.id, title='A')
        second = Task(project_id=project.id, title='B')
        db.add_all([first, second])
        db.flush()
        ids = (first.id, second.id)
        db.commit()

    def attempt(dependent, prerequisite):
        with session_factory()() as db:
            try:
                add_dependency(db, dependent, prerequisite)
                db.commit()
                return 'added'
            except TaskGraphError as exc:
                db.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda pair: attempt(*pair),
                               ((ids[0], ids[1]), (ids[1], ids[0]))))
    assert sorted(result) == ['added', 'cycle']
    with session_factory()() as db:
        assert len(db.scalars(select(TaskDependency)).all()) == 1
