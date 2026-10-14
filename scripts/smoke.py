"""Synthetic end-to-end check for the private Compose foundation."""
import argparse
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', default='http://localhost:8080')
parser.add_argument('--password-file', type=Path, default=Path('.local/initial_admin_password'))
args = parser.parse_args()
base = args.base_url.rstrip('/')
target = urlsplit(base)
if (target.scheme != 'http' or target.hostname not in ('localhost', '127.0.0.1', '::1')
        or target.username is not None or target.password is not None
        or target.path or target.query or target.fragment):
    parser.error('Smoke requires an HTTP loopback origin')
origin = {'Origin': base}
password = args.password_file.read_text().rstrip('\n')
with httpx.Client(base_url=base, trust_env=False, timeout=5) as c:
    assert c.get('/health/ready').json() == {'status': 'ready'}
    assert c.get('/api/projects').status_code == 401
    response = c.post('/api/auth/login', json={'password': password}, headers=origin)
    assert response.status_code == 200, response.text
    csrf = c.cookies['workforce_csrf']
    headers = {**origin, 'X-CSRF-Token': csrf}
    p = c.post('/api/projects', json={'name': 'Compose fixture'}, headers=headers)
    assert p.status_code == 201, p.text
    a = c.post('/api/agents', json={'name': 'Fixture agent', 'role': 'specialist', 'instructions': 'Synthetic only', 'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers)
    assert a.status_code == 201, a.text
    t = c.post('/api/tasks', json={'project_id': p.json()['id'], 'title': 'Check background execution'}, headers=headers)
    assert t.status_code == 201, t.text
    path = f"/api/tasks/{t.json()['id']}/dispatch"
    denied = c.post(path, json={'agent_id': a.json()['id'], 'root_cap': '1.0'}, headers=headers)
    assert denied.status_code == 403, denied.text
    grant = c.post(f"/api/agents/{a.json()['id']}/grants", json={'project_id': p.json()['id'], 'action': 'project.execute', 'allowed': True}, headers=headers)
    assert grant.status_code == 201, grant.text
    run = c.post(path, json={'agent_id': a.json()['id'], 'root_cap': '1.0'}, headers=headers)
    assert run.status_code == 202, run.text
    execution_id = run.json()['execution_id']
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status = c.get(f'/api/executions/{execution_id}').json()['status']
        if status == 'succeeded':
            break
        if status in ('failed', 'cancelled'):
            raise AssertionError(status)
        time.sleep(.3)
    else:
        raise AssertionError(f'Execution stayed {status}')
    tasks = c.get('/api/tasks', params={'project_id': p.json()['id']}).json()
    assert tasks[0]['status'] == 'review'
    audit = c.get('/api/activity').json()
    assert any(e['action'] == 'fixture.complete' and e['outcome'] == 'allowed' for e in audit)
    print('smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present')
