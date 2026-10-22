from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event

from dbos import DBOS
from sqlalchemy import select

from workforce.budgets import PriceEnvelope, reserve_shared_cost
from workforce.config import get_settings
from workforce.db import session_factory
from workforce.models import (AgentConfigVersion, Approval, ArtifactVersion, AuditEvent, BudgetAccount,
                              BudgetReservation, DailyBudgetAccount, Execution, ModelCall, Outbox)
from workforce.governed_call import governed_generate, price_for
from workforce.providers import (FakeAdapter, GenerationRequest, ProviderError,
                                 ProviderErrorKind, TextMessage)
from workforce.worker import dispatch_once


def setup_priced_execution(authenticated, monkeypatch, connection, model):
    monkeypatch.setenv('DAILY_CAP_USD', '1.0')
    get_settings.cache_clear()
    headers = {'Origin': 'http://localhost:8080', 'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Priced fixture'}, headers=headers).json()
    agent = authenticated.post('/api/agents', json={
        'name': 'Priced worker', 'role': 'specialist', 'instructions': 'Synthetic only',
        'provider_connection': connection, 'model_id': model}, headers=headers).json()
    task = authenticated.post('/api/tasks', json={'project_id': project['id'], 'title': 'Priced task'}, headers=headers).json()
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True}, headers=headers).status_code == 201
    envelope = PriceEnvelope(provider_connection=connection, model_id=model, source='synthetic-test',
        observed_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        max_input_tokens=500, max_output_tokens=128,
        input_usd_per_million=Decimal('1'), output_usd_per_million=Decimal('2'))
    update = authenticated.put(f"/api/agents/{agent['id']}/config", json={
        'expected_version': 1, 'instructions': 'Synthetic only',
        'provider_connection': connection, 'model_id': model,
        'price_envelope': envelope.model_dump(mode='json')}, headers=headers)
    assert update.status_code == 200, update.text
    history = authenticated.get(f"/api/agents/{agent['id']}/config").json()['versions']
    assert len(history) == 2 and history[1]['price_envelope'] == envelope.model_dump(mode='json')
    response = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={
        'agent_id': agent['id'], 'root_cap': '1.0'}, headers=headers)
    assert response.status_code == 202, response.text
    return response.json()['execution_id']


def test_price_config_rejects_mismatch_expiry_and_missing_daily_cap(authenticated, monkeypatch):
    headers = {'Origin': 'http://localhost:8080', 'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    agent = authenticated.post('/api/agents', json={'name': 'Config fixture', 'role': 'specialist',
        'instructions': 'Synthetic', 'provider_connection': 'fixture-alpha',
        'model_id': 'alpha-text-v1'}, headers=headers).json()
    envelope = PriceEnvelope(provider_connection='fixture-alpha', model_id='alpha-text-v1',
        source='synthetic-test', observed_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        max_input_tokens=500, max_output_tokens=128,
        input_usd_per_million=Decimal('1'), output_usd_per_million=Decimal('2'))
    payload = {'expected_version': 1, 'instructions': 'Synthetic', 'provider_connection': 'fixture-alpha',
               'model_id': 'alpha-text-v1', 'price_envelope': envelope.model_dump(mode='json')}
    endpoint = f"/api/agents/{agent['id']}/config"
    assert authenticated.put(endpoint, json=payload, headers=headers).status_code == 422
    monkeypatch.setenv('DAILY_CAP_USD', '1.0')
    get_settings.cache_clear()
    assert authenticated.put(endpoint, json={**payload, 'price_envelope': {
        **payload['price_envelope'], 'model_id': 'different'}}, headers=headers).status_code == 422
    assert authenticated.put(endpoint, json={**payload, 'price_envelope': {
        **payload['price_envelope'], 'expires_at': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}},
        headers=headers).status_code == 422
    assert authenticated.put(endpoint, json=payload, headers=headers).status_code == 200
    assert authenticated.put(endpoint, json=payload, headers=headers).status_code == 409


def launch():
    DBOS(config={'name': 'workforce-test', 'system_database_url':
        get_settings().workflow_url,
        'application_version': 'usage-normalization-v1'})
    DBOS.launch()


def test_priced_fixture_settles_once_and_replay_has_no_extra_effect(authenticated, monkeypatch):
    execution_id = setup_priced_execution(authenticated, monkeypatch, 'fixture-alpha', 'alpha-text-v1')
    launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'succeeded'
        with session_factory()() as db:
            assert db.get(Execution, execution_id).status == 'succeeded'
            hold = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == f'priced-model:{execution_id}'))
            assert hold.status == 'settled' and hold.actual > 0
            root = db.get(BudgetAccount, execution_id)
            daily = db.get(DailyBudgetAccount, hold.daily_day)
            assert root.reserved == daily.reserved == 0
            assert root.spent == daily.spent == hold.actual
            assert db.scalar(select(ModelCall).where(ModelCall.execution_id == execution_id)) is not None
            for row in db.scalars(select(Outbox)):
                row.delivered_at = None
            db.commit()
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'succeeded'
    finally:
        DBOS.destroy()
    with session_factory()() as db:
        assert len(db.scalars(select(ModelCall).where(ModelCall.execution_id == execution_id)).all()) == 1
        assert db.get(BudgetAccount, execution_id).spent == hold.actual
    headers = {'Origin': 'http://localhost:8080', 'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    assert authenticated.post(f'/api/executions/{execution_id}/cost-reconciliation', json={
        'expected_hold_amount': str(hold.amount), 'charged_usd': str(hold.actual),
        'evidence_reference': 'synthetic:cannot-rewrite-known-result'}, headers=headers).status_code == 409


def test_timeout_retains_shared_hold_and_is_unknown(authenticated, monkeypatch):
    execution_id = setup_priced_execution(authenticated, monkeypatch, 'fixture-timeout', 'timeout-v1')
    launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'unknown'
    finally:
        DBOS.destroy()
    with session_factory()() as db:
        hold = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == f'priced-model:{execution_id}'))
        assert hold.status == 'unknown' and hold.actual is None
        assert db.get(BudgetAccount, execution_id).reserved == hold.amount
        assert db.get(DailyBudgetAccount, hold.daily_day).reserved == hold.amount
        assert db.scalar(select(ModelCall).where(ModelCall.execution_id == execution_id)) is None


def test_malformed_post_dispatch_response_keeps_charge_unknown(authenticated, monkeypatch):
    execution_id = setup_priced_execution(authenticated, monkeypatch, 'fixture-alpha', 'alpha-text-v1')
    def malformed(_self, _request):
        raise ProviderError(ProviderErrorKind.MALFORMED_RESPONSE, 'Synthetic malformed response')
    monkeypatch.setattr(FakeAdapter, 'generate', malformed)
    launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'unknown'
    finally:
        DBOS.destroy()
    with session_factory()() as db:
        hold = db.scalar(select(BudgetReservation).where(
            BudgetReservation.invocation_key == f'priced-model:{execution_id}'))
        assert hold.status == 'unknown'
        assert db.get(BudgetAccount, execution_id).reserved == hold.amount
        assert db.get(DailyBudgetAccount, hold.daily_day).reserved == hold.amount
        event = db.scalar(select(AuditEvent).where(AuditEvent.effect_key == f'model-error:{execution_id}'))
        assert event.outcome == 'outcome_unknown'
        assert event.detail['provider_error'] == 'malformed_response'


def test_owner_reconciles_unknown_synthetic_charge_once(authenticated, monkeypatch):
    execution_id = setup_priced_execution(authenticated, monkeypatch, 'fixture-timeout', 'timeout-v1')
    launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'unknown'
    finally:
        DBOS.destroy()
    hold_url = f'/api/executions/{execution_id}/cost-hold'
    hold = authenticated.get(hold_url).json()
    assert hold['status'] == 'unknown' and hold['actual'] is None
    headers = {'Origin': 'http://localhost:8080', 'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    url = f'/api/executions/{execution_id}/cost-reconciliation'
    body = {'expected_hold_amount': str(hold['amount']), 'charged_usd': '0.000111',
            'evidence_reference': 'synthetic:effect-ledger/receipt-1'}
    assert authenticated.post(url, json=body,
                              headers={'Origin': 'http://localhost:8080'}).status_code == 403
    assert authenticated.post(url, json={**body, 'evidence_reference': 'unverified receipt'},
                              headers=headers).status_code == 422
    assert authenticated.post(url, json={**body, 'expected_hold_amount': '0.999999'},
                              headers=headers).status_code == 409
    first = authenticated.post(url, json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()['status'] == 'settled'
    assert authenticated.post(url, json=body, headers=headers).status_code == 200
    assert authenticated.post(url, json={**body, 'charged_usd': '0.000112'},
                              headers=headers).status_code == 409
    assert authenticated.post(url, json={**body, 'evidence_reference': 'synthetic:another'},
                              headers=headers).status_code == 409
    with session_factory()() as db:
        reservation = db.scalar(select(BudgetReservation).where(
            BudgetReservation.invocation_key == f'priced-model:{execution_id}'))
        root = db.get(BudgetAccount, execution_id)
        daily = db.get(DailyBudgetAccount, reservation.daily_day)
        assert reservation.actual == root.spent == daily.spent == Decimal('0.000111')
        assert root.reserved == daily.reserved == 0
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.effect_key ==
            f'cost-reconcile:{execution_id}')).all()) == 1
        assert db.scalar(select(ModelCall.id).where(ModelCall.execution_id == execution_id)) is None


def test_replay_of_pre_call_commit_never_reissues_uncertain_request(authenticated, monkeypatch):
    execution_id = setup_priced_execution(authenticated, monkeypatch, 'fixture-alpha', 'alpha-text-v1')
    with session_factory()() as db:
        execution = db.get(Execution, execution_id)
        config = db.get(AgentConfigVersion, execution.config_version_id)
        price = price_for(config)
        hold = reserve_shared_cost(db, execution.root_id, datetime.now(timezone.utc).date(),
            f'priced-model:{execution_id}', price.upper_bound(), Decimal('1.0'))
        hold.status = 'calling'  # crash after pre-call commit; call outcome is unknowable
        db.commit()
    request = GenerationRequest(request_id=execution_id, model_id='alpha-text-v1',
        messages=(TextMessage(role='user', trust_origin='human', text='Synthetic task'),),
        max_output_tokens=128)
    def unexpected_generate(_request):
        raise AssertionError('Uncertain request was reissued')
    monkeypatch.setattr('workforce.providers.FakeAdapter.generate', unexpected_generate)
    assert governed_generate(execution_id, request, price) == {'error': 'outcome_unknown', 'retryable': False}
    with session_factory()() as db:
        hold = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == f'priced-model:{execution_id}'))
        assert hold.status == 'unknown'
        assert db.get(BudgetAccount, execution_id).reserved == hold.amount
        assert db.scalar(select(ModelCall).where(ModelCall.execution_id == execution_id)) is None


def test_cancelled_execution_never_acquires_priced_hold(authenticated, monkeypatch):
    execution_id = setup_priced_execution(authenticated, monkeypatch, 'fixture-alpha', 'alpha-text-v1')
    with session_factory()() as db:
        execution = db.get(Execution, execution_id)
        price = price_for(db.get(AgentConfigVersion, execution.config_version_id))
        execution.cancelled = True
        db.commit()
    request = GenerationRequest(request_id=execution_id, model_id='alpha-text-v1',
        messages=(TextMessage(role='user', trust_origin='human', text='Synthetic task'),),
        max_output_tokens=128)
    assert governed_generate(execution_id, request, price) == {'error': 'cancelled', 'retryable': False}
    with session_factory()() as db:
        assert db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == f'priced-model:{execution_id}')) is None
        assert db.scalar(select(ModelCall).where(ModelCall.execution_id == execution_id)) is None


def test_cancel_during_priced_call_blocks_following_artifact_effect(authenticated, monkeypatch):
    execution_id = setup_priced_execution(authenticated, monkeypatch, 'fixture-alpha', 'alpha-text-v1')
    started, proceed = Event(), Event()
    original_generate = FakeAdapter.generate
    def paused_generate(self, request):
        started.set()
        assert proceed.wait(10), 'Synthetic call was not released'
        return original_generate(self, request)
    monkeypatch.setattr(FakeAdapter, 'generate', paused_generate)
    launch()
    try:
        assert dispatch_once() == 1
        assert started.wait(10), 'Synthetic call did not start'
        headers = {'Origin': 'http://localhost:8080', 'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
        assert authenticated.post(f'/api/executions/{execution_id}/cancel', headers=headers).status_code == 200
        proceed.set()
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'cancelled'
    finally:
        proceed.set()
        DBOS.destroy()
    with session_factory()() as db:
        hold = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == f'priced-model:{execution_id}'))
        assert hold.status == 'settled' and hold.actual > 0  # a completed call can still cost money
        assert db.get(Execution, execution_id).status == 'cancelled'
        assert db.scalar(select(ModelCall).where(ModelCall.execution_id == execution_id)) is not None
        assert db.scalar(select(Approval.id).where(Approval.execution_id == execution_id)) is None
        assert db.scalar(select(ArtifactVersion.id).where(ArtifactVersion.execution_id == execution_id)) is None
