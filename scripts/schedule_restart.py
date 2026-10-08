"""Manual Compose recovery check: prepare, stop worker, wait past due, start worker, finish."""
import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

BASE = 'http://localhost:8080'


def login():
    client = httpx.Client(base_url=BASE, trust_env=False, timeout=5)
    password = Path('.local/initial_admin_password').read_text().rstrip('\n')
    response = client.post('/api/auth/login', json={'password': password},
                           headers={'Origin': BASE})
    assert response.status_code == 200, response.text
    return client, {'Origin': BASE,
                    'X-CSRF-Token': client.cookies['workforce_csrf']}


def post(client, path, body, headers):
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def prepare(path: Path):
    client, headers = login()
    try:
        due = (datetime.now(timezone.utc) + timedelta(seconds=105)).replace(
            second=0, microsecond=0)
        project = post(client, '/api/projects', {'name': 'Schedule restart fixture'}, headers)
        agent = post(client, '/api/agents', {
            'name': 'Schedule restart agent', 'role': 'specialist',
            'instructions': 'Synthetic schedule result',
            'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers)
        post(client, f"/api/agents/{agent['id']}/grants", {
            'project_id': project['id'], 'action': 'project.execute',
            'allowed': True}, headers)
        schedule = post(client, '/api/schedules', {
            'project_id': project['id'], 'agent_id': agent['id'],
            'title': 'Scheduled synthetic review', 'timezone': 'UTC',
            'local_time': due.strftime('%H:%M'), 'root_cap': '1.0'}, headers)
        post(client, f"/api/schedules/{schedule['id']}/state", {
            'enabled': True, 'expected_revision': schedule['revision']}, headers)
        path.write_text(json.dumps({'schedule_id': schedule['id'],
                                    'due': due.isoformat()}))
        print(f'prepare=passed; due={due.isoformat()}; stop worker now')
    finally:
        client.close()


def finish(path: Path):
    state = json.loads(path.read_text())
    due = datetime.fromisoformat(state['due'])
    assert datetime.now(timezone.utc) > due, 'Worker must restart after due time'
    client, _ = login()
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            rows = client.get(f"/api/schedules/{state['schedule_id']}/occurrences").json()
            if rows:
                break
            time.sleep(.3)
        else:
            raise AssertionError('No recovered occurrence')
        assert len(rows) == 1 and rows[0]['status'] == 'queued', rows
        assert datetime.fromisoformat(
            rows[0]['scheduled_for'].replace('Z', '+00:00')) == due
        execution_id = rows[0]['execution_id']
        while time.monotonic() < deadline:
            status = client.get(f'/api/executions/{execution_id}').json()['status']
            if status == 'succeeded':
                break
            if status in ('failed', 'cancelled', 'unknown'):
                raise AssertionError(status)
            time.sleep(.3)
        else:
            raise AssertionError('Recovered execution did not complete')
        print('finish=passed; occurrences=1; execution=succeeded')
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('prepare', 'finish'))
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    (prepare if args.stage == 'prepare' else finish)(args.state)
