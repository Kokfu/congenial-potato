"""Real API/DBOS worker path with native SDKs confined to in-memory HTTP."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import anthropic
from dbos import DBOS
import httpx2
import openai
import pytest
from sqlalchemy import select

from workforce import providers, worker
from workforce.budgets import PriceEnvelope
from workforce.config import get_settings
from workforce.db import session_factory
from workforce.models import (Approval, AuditEvent, BudgetAccount, BudgetReservation,
                              DailyBudgetAccount, Execution, ModelCall, Outbox)
from workforce.native_providers import AnthropicTextAdapter, OpenAITextAdapter
from workforce.providers import Capabilities, ProviderRegistry, registry as running_registry

MODEL = 'offline-text-v1'
CAPABILITIES = Capabilities(max_input_tokens=4096, max_output_tokens=256, usage_reported=True)


def offline_adapter(kind: str, requests: list[dict], malformed: bool):
    def handle(request):
        payload = json.loads(request.content)
        requests.append({'path': request.url.path, 'body': payload})
        if kind == 'openai':
            assert request.url.path == '/v1/responses'
            return httpx2.Response(200, json={
                'id': 'resp_offline', 'object': 'response', 'created_at': 0,
                'status': 'completed', 'model': MODEL,
                'output': [] if malformed else [{'id': 'msg_offline', 'type': 'message', 'role': 'assistant',
                            'status': 'completed', 'content': [
                                {'type': 'output_text', 'text': 'Offline SDK result', 'annotations': []}]}],
                'usage': {'input_tokens': 4, 'output_tokens': 2, 'total_tokens': 6,
                          'input_tokens_details': {'cached_tokens': 1, 'cache_write_tokens': 1},
                          'output_tokens_details': {'reasoning_tokens': 1}}})
        assert request.url.path == '/v1/messages'
        return httpx2.Response(200, json={
            'id': 'msg_offline', 'type': 'message', 'role': 'assistant', 'model': MODEL,
            'content': [{'type': 'text', 'text': 'Offline SDK result'}],
            'stop_reason': 'end_turn', 'stop_sequence': None,
            'usage': {'input_tokens': 4, 'cache_creation_input_tokens': 2,
                      'cache_read_input_tokens': 3, 'output_tokens': 2,
                      'output_tokens_details': {'thinking_tokens': 1}}})

    transport = httpx2.MockTransport(handle)
    if kind == 'openai':
        client = openai.OpenAI(api_key='synthetic-only', max_retries=0,
                               http_client=httpx2.Client(transport=transport))
        return OpenAITextAdapter({MODEL: CAPABILITIES}, client=client)
    client = anthropic.Anthropic(api_key='synthetic-only', max_retries=0,
                                 http_client=httpx2.Client(transport=transport))
    return AnthropicTextAdapter({MODEL: CAPABILITIES}, client=client)


@pytest.mark.parametrize('kind,expected_input,malformed', [
    ('openai', 4, False), ('anthropic', 9, False), ('openai', None, True)])
def test_offline_native_sdk_is_governed_through_api_and_worker(authenticated, monkeypatch,
                                                                kind, expected_input, malformed):
    assert 'openai-native' not in running_registry.connections()
    assert 'anthropic-native' not in running_registry.connections()
    requests = []
    adapter = offline_adapter(kind, requests, malformed)
    test_registry = ProviderRegistry((adapter,))
    monkeypatch.setattr(providers, 'registry', test_registry)
    monkeypatch.setenv('DAILY_CAP_USD', '1.0')
    get_settings.cache_clear()
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': f'Offline {kind}'}, headers=headers).json()
    agent_response = authenticated.post('/api/agents', json={
        'name': 'SDK fixture agent', 'role': 'specialist', 'instructions': 'Stay concise.',
        'provider_connection': adapter.connection_id, 'model_id': MODEL}, headers=headers)
    assert agent_response.status_code == 201, agent_response.text
    agent = agent_response.json()
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=headers).status_code == 201
    observed = datetime.now(timezone.utc)
    price = PriceEnvelope(provider_connection=adapter.connection_id, model_id=MODEL,
        source='in-memory-sdk-fixture', observed_at=observed,
        expires_at=observed + timedelta(days=1), max_input_tokens=500,
        max_output_tokens=128, input_usd_per_million=Decimal('1'),
        output_usd_per_million=Decimal('2'))
    update = authenticated.put(f"/api/agents/{agent['id']}/config", json={
        'expected_version': 1, 'instructions': 'Stay concise.',
        'provider_connection': adapter.connection_id, 'model_id': MODEL,
        'price_envelope': price.model_dump(mode='json')}, headers=headers)
    assert update.status_code == 200, update.text
    task = authenticated.post('/api/tasks', json={
        'project_id': project['id'], 'title': 'Generate offline text'}, headers=headers).json()
    dispatch = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={
        'agent_id': agent['id'], 'root_cap': '1.0'}, headers=headers)
    assert dispatch.status_code == 202, dispatch.text
    execution_id = dispatch.json()['execution_id']

    DBOS(config={'name': 'workforce-test', 'system_database_url':
        'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
        'application_version': 'usage-normalization-v1'})
    DBOS.launch()
    expected_status = 'unknown' if malformed else 'succeeded'
    try:
        assert worker.dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == expected_status
        with session_factory()() as db:
            for row in db.scalars(select(Outbox)):
                row.delivered_at = None
            db.commit()
        assert worker.dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == expected_status
    finally:
        DBOS.destroy()

    assert len(requests) == 1
    assert requests[0]['body']['model'] == MODEL
    if kind == 'openai':
        assert requests[0]['body']['store'] is False
    with session_factory()() as db:
        execution = db.get(Execution, execution_id)
        hold = db.scalar(select(BudgetReservation).where(
            BudgetReservation.invocation_key == f'priced-model:{execution_id}'))
        call = db.scalar(select(ModelCall).where(ModelCall.execution_id == execution_id))
        root = db.get(BudgetAccount, execution_id)
        daily = db.get(DailyBudgetAccount, hold.daily_day)
        assert execution.config_version_id == update.json()['config_version_id']
        if malformed:
            assert execution.status == hold.status == 'unknown'
            assert call is None and hold.actual is None
            assert root.reserved == daily.reserved == hold.amount
            assert root.spent == daily.spent == 0
            assert db.scalar(select(Approval.id).where(Approval.execution_id == execution_id)) is None
            error = db.scalar(select(AuditEvent).where(
                AuditEvent.effect_key == f'model-error:{execution_id}'))
            assert error.detail['provider_error'] == 'malformed_response'
        else:
            assert (execution.status, hold.status, call.provider, call.model_id) == (
                'succeeded', 'settled', adapter.connection_id, MODEL)
            assert call.usage['input_tokens'] == expected_input
            assert call.usage['cached_input_tokens'] == (1 if kind == 'openai' else 3)
            assert root.spent == daily.spent == hold.actual == price.actual_cost(expected_input, 2)
            assert root.reserved == daily.reserved == 0
            assert len(db.scalars(select(ModelCall)).all()) == 1
            assert len(db.scalars(select(Approval).where(Approval.execution_id == execution_id)).all()) == 1
