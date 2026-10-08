from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import (AgentProjectGrant, AuditEvent, BudgetAccount,
                              Execution, Outbox, Schedule, ScheduleOccurrence, Task)
from workforce.schedule_dispatch import schedule_due_once


def _schedule(authenticated):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Due fixture'},
                                 headers=headers).json()
    agent = authenticated.post('/api/agents', json={
        'name': 'Due agent', 'role': 'specialist', 'instructions': 'Fixture',
        'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers).json()
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=headers).status_code == 201
    created = authenticated.post('/api/schedules', json={
        'project_id': project['id'], 'agent_id': agent['id'],
        'title': 'Scheduled review', 'timezone': 'UTC', 'local_time': '10:00',
        'root_cap': '0.500000'}, headers=headers)
    assert created.status_code == 201
    row = created.json()
    assert authenticated.post(f"/api/schedules/{row['id']}/state", json={
        'enabled': True, 'expected_revision': row['revision']},
        headers=headers).status_code == 200
    return project, agent, row['id'], headers


def test_restart_replay_and_concurrent_tick_admit_one_occurrence(authenticated):
    project, _, schedule_id, _ = _schedule(authenticated)
    at = datetime(2030, 1, 2, 12, 0, tzinfo=timezone.utc)
    with session_factory()() as db:
        schedule = db.get(Schedule, schedule_id)
        schedule.last_checked_at = at - timedelta(days=2)
        db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: schedule_due_once(at=at), range(2)))
    assert sorted(results) == [0, 1]
    assert schedule_due_once(at=at) == 0
    assert schedule_due_once(at=at - timedelta(hours=1)) == 0
    with session_factory()() as db:
        assert db.get(Schedule, schedule_id).last_checked_at == at
        rows = db.scalars(select(ScheduleOccurrence)).all()
        assert len(rows) == 1 and rows[0].status == 'queued'
        assert rows[0].local_date.isoformat() == '2030-01-02'
        execution = db.get(Execution, rows[0].execution_id)
        task = db.get(Task, execution.task_id)
        assert task.project_id == project['id']
        assert task.work_key == f'{schedule_id}:2030-01-02'
        assert db.get(BudgetAccount, execution.id).cap == 0.5
        assert db.scalar(select(Outbox.id).where(
            Outbox.idempotency_key == execution.workflow_id)) is not None
        assert db.scalar(select(AuditEvent.id).where(
            AuditEvent.effect_key == f'schedule:{schedule_id}:2030-01-02')) is not None


def test_overlap_and_revocation_skip_with_audited_reasons(authenticated):
    _, agent, schedule_id, _ = _schedule(authenticated)
    first = datetime(2030, 1, 2, 12, 0, tzinfo=timezone.utc)
    with session_factory()() as db:
        schedule = db.get(Schedule, schedule_id)
        schedule.last_checked_at = first - timedelta(days=2)
        db.commit()
    assert schedule_due_once(at=first) == 1
    second = first + timedelta(days=1)
    assert schedule_due_once(at=second) == 0
    with session_factory()() as db:
        rows = db.scalars(select(ScheduleOccurrence).order_by(
            ScheduleOccurrence.local_date)).all()
        assert [(row.status, row.reason) for row in rows] == [
            ('queued', None), ('skipped', 'prior_active')]
        execution = db.get(Execution, rows[0].execution_id)
        db.get(Task, execution.task_id).status = 'completed'
        grant = db.scalar(select(AgentProjectGrant).where(
            AgentProjectGrant.agent_id == agent['id']))
        grant.allowed = False
        db.commit()
    assert schedule_due_once(at=second + timedelta(days=1)) == 0
    with session_factory()() as db:
        rows = db.scalars(select(ScheduleOccurrence).order_by(
            ScheduleOccurrence.local_date)).all()
        assert len(rows) == 3
        assert rows[-1].reason == 'project_grant_denied'
        assert len(db.scalars(select(Execution)).all()) == 1


def test_disabled_schedule_never_dispatches(authenticated):
    _, _, schedule_id, headers = _schedule(authenticated)
    state = authenticated.post(f'/api/schedules/{schedule_id}/state', json={
        'enabled': False, 'expected_revision': 2}, headers=headers)
    assert state.status_code == 200
    assert authenticated.post(f'/api/schedules/{schedule_id}/state', json={
        'enabled': True, 'expected_revision': 2}, headers=headers).status_code == 409
    assert schedule_due_once(at=datetime(2030, 1, 2, 12, tzinfo=timezone.utc)) == 0
    assert authenticated.get(f'/api/schedules/{schedule_id}/occurrences').json() == []
