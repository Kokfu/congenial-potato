"""Private, synthetic provider-switch proof against the Compose deployment."""
import time
from pathlib import Path

import httpx

base = 'http://localhost:8080'
password = Path('.local/initial_admin_password').read_text().strip()

with httpx.Client(base_url=base, trust_env=False, timeout=5) as client:
    assert client.post('/api/auth/login', json={'password': password}, headers={'Origin': base}).status_code == 200
    headers = {'Origin': base, 'X-CSRF-Token': client.cookies['workforce_csrf']}
    project = client.post('/api/projects', json={'name': 'Provider switch fixture'}, headers=headers).json()
    agent_response = client.post('/api/agents', json={
        'name': 'Switchable fixture', 'role': 'specialist', 'instructions': 'First config',
        'provider_connection': 'fixture-alpha', 'model_id': 'alpha-text-v1'}, headers=headers)
    assert agent_response.status_code == 201, agent_response.text
    agent_id = agent_response.json()['id']
    assert client.post(f'/api/agents/{agent_id}/grants', json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True}, headers=headers).status_code == 201

    def run(title: str) -> tuple[str, dict]:
        task = client.post('/api/tasks', json={'project_id': project['id'], 'title': title}, headers=headers).json()
        response = client.post(f"/api/tasks/{task['id']}/dispatch", json={
            'agent_id': agent_id, 'root_cap': '1.0'}, headers=headers)
        assert response.status_code == 202, response.text
        execution_id = response.json()['execution_id']
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = client.get(f'/api/executions/{execution_id}').json()
            if state['status'] == 'succeeded':
                return state['config_version_id'], client.get(f'/api/executions/{execution_id}/model-call').json()
            assert state['status'] not in ('failed', 'cancelled'), state
            time.sleep(.3)
        raise AssertionError('Fixture execution timed out')

    first_config, first_call = run('Before provider switch')
    update = client.put(f'/api/agents/{agent_id}/config', json={
        'expected_version': 1, 'instructions': 'Second config',
        'provider_connection': 'fixture-beta', 'model_id': 'beta-tools-v1'}, headers=headers)
    assert update.status_code == 200, update.text
    second_config, second_call = run('After provider switch')
    assert first_config != second_config
    assert (first_call['provider_connection'], first_call['model_id']) == ('fixture-alpha', 'alpha-text-v1')
    assert (second_call['provider_connection'], second_call['model_id']) == ('fixture-beta', 'beta-tools-v1')
    assert first_call['usage']['reported_cost_usd'] is None
    assert second_call['usage']['reported_cost_usd'] is None
    assert len(client.get(f'/api/agents/{agent_id}/config').json()['versions']) == 2
    print('provider_switch=passed;agent_identity=stable;config_versions=2;fake_calls=2;cost=unknown')
