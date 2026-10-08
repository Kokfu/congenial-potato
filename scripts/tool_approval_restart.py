"""Synthetic Compose approval wait across API/worker restart.

Run `prepare`, restart `api worker`, then run `finish` with the same state path.
"""
import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

BASE = 'http://localhost:8080'


def login() -> tuple[httpx.Client, dict]:
    client = httpx.Client(base_url=BASE, trust_env=False, timeout=5)
    password = Path('.local/initial_admin_password').read_text().rstrip('\n')
    response = client.post('/api/auth/login', json={'password': password},
                           headers={'Origin': BASE})
    assert response.status_code == 200, response.text
    return client, {'Origin': BASE,
                    'X-CSRF-Token': client.cookies['workforce_csrf']}


def post(client: httpx.Client, path: str, body: dict, headers: dict) -> dict:
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def prepare(state_path: Path) -> None:
    client, headers = login()
    try:
        project = post(client, '/api/projects', {'name': 'Tool approval restart fixture'},
                       headers)
        payload = {'version': 1, 'action': 'project.artifact.write',
                   'arguments': {'project_id': project['id'],
                                 'artifact_id': str(uuid4()),
                                 'content': 'Synthetic restart effect: do not execute',
                                 'expected_parent': None}}
        agent = post(client, '/api/agents', {
            'name': 'Approval fixture', 'role': 'specialist',
            'instructions': 'FIXTURE_TOOL_JSON:' + json.dumps(payload),
            'provider_connection': 'fixture-tool', 'model_id': 'tool-v1',
            'output_contract': 'tool.v1'}, headers)
        task = post(client, '/api/tasks', {'project_id': project['id'],
                                           'title': 'Wait for synthetic approval'}, headers)
        post(client, f"/api/agents/{agent['id']}/grants", {
            'project_id': project['id'], 'action': 'project.execute',
            'allowed': True}, headers)
        for subject_agent, effect in [(None, 'require_approval'),
                                      (agent['id'], 'allow')]:
            post(client, '/api/tool-policies', {
                'project_id': project['id'], 'agent_id': subject_agent,
                'action': 'project.artifact.write', 'effect': effect}, headers)
        run = post(client, f"/api/tasks/{task['id']}/dispatch", {
            'agent_id': agent['id'], 'root_cap': '1.0'}, headers)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            rows = client.get('/api/tool-invocations',
                              params={'project_id': project['id']}).json()
            if rows:
                break
            time.sleep(.3)
        else:
            raise AssertionError('Tool proposal was not persisted')
        assert len(rows) == 1 and rows[0]['status'] == 'awaiting_approval', rows
        assert rows[0]['approval']['status'] == 'pending', rows
        state_path.write_text(json.dumps({'project_id': project['id'],
                                          'execution_id': run['execution_id'],
                                          'invocation_id': rows[0]['id'],
                                          'approval_id': rows[0]['approval']['id'],
                                          'payload_hash': rows[0]['approval']['payload_hash']}))
        print('prepare=passed; approval=pending; tool_effects=0')
    finally:
        client.close()


def finish(state_path: Path) -> None:
    state = json.loads(state_path.read_text())
    client, headers = login()
    try:
        rows = client.get('/api/tool-invocations',
                          params={'project_id': state['project_id']}).json()
        row = next(item for item in rows if item['id'] == state['invocation_id'])
        assert row['approval']['id'] == state['approval_id']
        assert row['approval']['status'] == 'pending'
        response = post(client, f"/api/tool-invocations/{row['id']}/decision", {
            'approved': True, 'payload_hash': state['payload_hash']}, headers)
        assert response['status'] == 'admitted'
        assert response['approval_status'] == 'approved'
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = client.get('/api/tool-invocations',
                                 params={'project_id': state['project_id']}).json()[0]
            if current['status'] == 'succeeded':
                break
            if current['status'] in ('failed', 'invalidated', 'unknown'):
                raise AssertionError(current)
            time.sleep(.3)
        else:
            raise AssertionError(f"Tool stayed {current['status']}")
        assert current['result']['simulated'] is True
        assert client.get('/api/artifacts', params={
            'project_id': state['project_id']}).json() == []
        print('finish=passed; approval=approved; invocation=succeeded; synthetic_effects=1; artifact_versions=0')
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('prepare', 'finish'))
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    (prepare if args.stage == 'prepare' else finish)(args.state)
