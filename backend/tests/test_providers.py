import pytest
from datetime import datetime, timedelta, timezone

from workforce.providers import (GenerationRequest, ProviderError, ProviderErrorKind,
                                 ProviderRegistry, TextMessage, fixture_registry)
from sqlalchemy import select
from workforce.db import session_factory
from workforce.models import AgentProjectGrant, AuditEvent, BudgetAccount, Execution, ModelCall, Outbox, Task


def request(model_id: str, **requirements) -> GenerationRequest:
    return GenerationRequest(request_id='fixture-request', model_id=model_id,
                             messages=(TextMessage(role='user', trust_origin='human', text='Write a brief fixture.'),),
                             max_output_tokens=32, **requirements)


def test_fake_adapters_discovery_capabilities_and_unknown_usage():
    registry = fixture_registry()
    assert {'fixture-alpha', 'fixture-beta'} <= set(registry.connections())
    alpha = registry.get('fixture-alpha')
    beta = registry.get('fixture-beta')
    first = alpha.discover_models()
    assert alpha.discover_models() is first
    refreshed = alpha.discover_models(refresh=True)
    assert refreshed.origin == 'fixture' and refreshed.observed_at >= first.observed_at
    assert beta.describe_capabilities('beta-tools-v1').tool_calls
    assert not alpha.describe_capabilities('alpha-text-v1').tool_calls
    response = alpha.generate(request('alpha-text-v1'))
    assert response.actual_model == 'alpha-text-v1'
    assert response.usage.reported_cost_usd is None
    with pytest.raises(ProviderError) as expired:
        alpha.generate(request('alpha-text-v1').model_copy(update={
            'deadline_at': datetime.now(timezone.utc) - timedelta(seconds=1)}))
    assert expired.value.kind == ProviderErrorKind.TIMEOUT
    assert alpha.estimate_usage(request('alpha-text-v1')).cost_upper_bound_usd is None
    streamed = list(alpha.stream(request('alpha-text-v1')))
    assert streamed[-1].kind == 'final' and streamed[-1].response == response


def test_unsupported_capabilities_and_models_fail_closed():
    registry = fixture_registry()
    alpha = registry.get('fixture-alpha')
    with pytest.raises(ProviderError) as missing:
        alpha.generate(request('invented-model'))
    assert missing.value.kind == ProviderErrorKind.UNAVAILABLE_MODEL
    with pytest.raises(ProviderError) as incompatible:
        alpha.generate(request('alpha-text-v1', require_tools=True))
    assert incompatible.value.kind == ProviderErrorKind.CAPABILITY
    assert not incompatible.value.retryable
    assert registry.get('fixture-beta').generate(request('beta-tools-v1', require_tools=True)).content
    with pytest.raises(ProviderError) as unavailable:
        registry.get('unconfigured')
    assert unavailable.value.kind == ProviderErrorKind.INVALID_REQUEST


def test_duplicate_provider_connection_is_rejected():
    adapter = fixture_registry().get('fixture-alpha')
    with pytest.raises(ValueError, match='Duplicate'):
        ProviderRegistry((adapter, adapter))


def test_agent_switch_keeps_identity_grants_and_execution_config(authenticated):
    headers = {'Origin': 'http://localhost:8080', 'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    catalog = authenticated.get('/api/provider-connections?refresh=true').json()
    assert {'fixture-alpha', 'fixture-beta'} <= {item['connection_id'] for item in catalog}
    project = authenticated.post('/api/projects', json={'name': 'Switch fixture'}, headers=headers).json()
    agent = authenticated.post('/api/agents', json={'name': 'Stable worker', 'role': 'specialist',
        'instructions': 'First revision', 'provider_connection': 'fixture-alpha', 'model_id': 'alpha-text-v1'}, headers=headers).json()
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={'project_id': project['id'],
        'action': 'project.execute', 'allowed': True}, headers=headers).status_code == 201

    def dispatch(title):
        task = authenticated.post('/api/tasks', json={'project_id': project['id'], 'title': title}, headers=headers).json()
        response = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={'agent_id': agent['id'], 'root_cap': '1.0'}, headers=headers)
        assert response.status_code == 202, response.text
        return response.json()['execution_id']

    first = dispatch('Before switch')
    update = {'expected_version': 1, 'instructions': 'Second revision',
              'provider_connection': 'fixture-beta', 'model_id': 'beta-tools-v1'}
    changed = authenticated.put(f"/api/agents/{agent['id']}/config", json=update, headers=headers)
    assert changed.status_code == 200 and changed.json()['version'] == 2
    assert authenticated.put(f"/api/agents/{agent['id']}/config", json=update, headers=headers).status_code == 409
    assert authenticated.put(f"/api/agents/{agent['id']}/config", json={**update, 'expected_version': 2,
        'model_id': 'invented-model'}, headers=headers).status_code == 422
    second = dispatch('After switch')
    history = authenticated.get(f"/api/agents/{agent['id']}/config").json()['versions']
    assert [(v['version'], v['provider_connection']) for v in history] == [(1, 'fixture-alpha'), (2, 'fixture-beta')]
    assert authenticated.get('/api/agents').json()[0]['id'] == agent['id']
    with session_factory()() as db:
        assert db.get(Execution, first).config_version_id == history[0]['id']
        assert db.get(Execution, second).config_version_id == history[1]['id']
        assert db.scalar(select(AgentProjectGrant.id).where(AgentProjectGrant.agent_id == agent['id'])) is not None
    from dbos import DBOS
    from workforce.worker import dispatch_once
    DBOS(config={'name': 'workforce-test', 'system_database_url':
                 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
                 'application_version': 'provider-boundary-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 2
        assert DBOS.retrieve_workflow(f'execution:{first}').get_result() == 'succeeded'
        assert DBOS.retrieve_workflow(f'execution:{second}').get_result() == 'succeeded'
        with session_factory()() as db:
            for row in db.scalars(select(Outbox).where(Outbox.kind == 'execution.dispatch')):
                row.delivered_at = None
            db.commit()
        assert dispatch_once() == 2
        assert DBOS.retrieve_workflow(f'execution:{first}').get_result() == 'succeeded'
        assert DBOS.retrieve_workflow(f'execution:{second}').get_result() == 'succeeded'
    finally:
        DBOS.destroy()
    with session_factory()() as db:
        before, after = db.get(ModelCall, db.scalar(select(ModelCall.id).where(ModelCall.execution_id == first))), db.get(ModelCall, db.scalar(select(ModelCall.id).where(ModelCall.execution_id == second)))
        assert (before.provider, before.model_id) == ('fixture-alpha', 'alpha-text-v1')
        assert (after.provider, after.model_id) == ('fixture-beta', 'beta-tools-v1')
        assert before.usage['reported_cost_usd'] is None
        assert len(db.scalars(select(ModelCall)).all()) == 2


def test_timeout_fixture_releases_budget_without_model_effect(authenticated):
    from dbos import DBOS
    from workforce.worker import dispatch_once
    headers = {'Origin': 'http://localhost:8080', 'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Timeout fixture'}, headers=headers).json()
    agent = authenticated.post('/api/agents', json={'name': 'Timeout worker', 'role': 'specialist',
        'instructions': 'Synthetic only', 'provider_connection': 'fixture-timeout', 'model_id': 'timeout-v1'}, headers=headers).json()
    task = authenticated.post('/api/tasks', json={'project_id': project['id'], 'title': 'Timeout task'}, headers=headers).json()
    authenticated.post(f"/api/agents/{agent['id']}/grants", json={'project_id': project['id'],
        'action': 'project.execute', 'allowed': True}, headers=headers)
    response = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={'agent_id': agent['id'], 'root_cap': '1.0'}, headers=headers)
    assert response.status_code == 202
    execution_id = response.json()['execution_id']
    DBOS(config={'name': 'workforce-test', 'system_database_url':
                 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
                 'application_version': 'provider-boundary-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'failed'
    finally:
        DBOS.destroy()
    with session_factory()() as db:
        assert db.get(Execution, execution_id).status == 'failed'
        assert db.get(Task, task['id']).status == 'failed'
        assert db.get(BudgetAccount, execution_id).reserved == 0
        assert db.scalar(select(ModelCall.id).where(ModelCall.execution_id == execution_id)) is None
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.effect_key == f'model-error:{execution_id}')) is not None
