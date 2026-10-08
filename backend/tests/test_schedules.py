from datetime import datetime, timezone

from workforce.schedules import daily_instant, latest_due


def test_daily_occurrence_coalesces_and_bounds_downtime():
    now = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
    due = latest_due('schedule-1', 'Asia/Kuala_Lumpur', 16, 0,
                     after=datetime(2026, 10, 5, tzinfo=timezone.utc), now=now)
    assert due is not None
    assert due.key == 'schedule-1:2026-10-08'
    assert due.scheduled_for == datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)
    assert latest_due('schedule-1', 'Asia/Kuala_Lumpur', 16, 0,
                      after=due.scheduled_for, now=now) is None
    assert latest_due('schedule-1', 'Asia/Kuala_Lumpur', 16, 0,
                      after=now, now=now) is None
    assert latest_due('schedule-1', 'UTC', 8, 0,
                      after=datetime(2026, 10, 8, 8, 1, tzinfo=timezone.utc),
                      now=now) is None


def test_dst_skips_gap_and_chooses_first_fold():
    from datetime import date
    assert daily_instant(date(2026, 3, 8), 'America/New_York', 2, 30) is None
    assert daily_instant(date(2026, 11, 1), 'America/New_York', 1, 30) == (
        datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc))
    now = datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc)
    assert latest_due('s', 'America/New_York', 2, 30,
                      after=datetime(2026, 3, 7, 9, 0, tzinfo=timezone.utc),
                      now=now) is None


def test_schedule_definition_requires_project_grant_and_valid_timezone(authenticated):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Scheduled project'},
                                 headers=headers).json()
    other = authenticated.post('/api/projects', json={'name': 'Foreign project'},
                               headers=headers).json()
    agent = authenticated.post('/api/agents', json={
        'name': 'Scheduled fixture', 'role': 'specialist', 'instructions': 'Fixture',
        'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers).json()
    body = {'project_id': project['id'], 'agent_id': agent['id'],
            'title': 'Daily review', 'timezone': 'Asia/Kuala_Lumpur',
            'local_time': '16:00', 'root_cap': '1.000000'}
    assert authenticated.post('/api/schedules', json=body, headers=headers).status_code == 403
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': other['id'], 'action': 'project.execute', 'allowed': True},
        headers=headers).status_code == 201
    assert authenticated.post('/api/schedules', json=body, headers=headers).status_code == 403
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=headers).status_code == 201
    assert authenticated.post('/api/schedules', json={**body, 'timezone': 'No/Such_Zone'},
                              headers=headers).status_code == 422
    assert authenticated.post('/api/schedules', json={**body, 'local_time': '24:00'},
                              headers=headers).status_code == 422
    assert authenticated.post('/api/schedules', json={**body, 'root_cap': '0'},
                              headers=headers).status_code == 422
    created = authenticated.post('/api/schedules', json=body, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()['enabled'] is False
    assert created.json()['local_time'] == '16:00'
    rows = authenticated.get('/api/schedules', params={'project_id': project['id']}).json()
    assert len(rows) == 1 and rows[0]['id'] == created.json()['id']
    assert authenticated.get('/api/schedules', params={'project_id': other['id']}).json() == []
