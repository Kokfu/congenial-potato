from datetime import datetime, timedelta, timezone
from decimal import Decimal

from dbos import DBOS
from sqlalchemy import select

from test_plans import setup_manager
from workforce.budgets import PriceEnvelope, reserve_shared_cost, settle_shared_cost
from workforce.config import get_settings
from workforce.db import session_factory
from workforce.models import (BudgetAccount, BudgetReservation, DailyBudgetAccount,
                              Execution, ModelCall, Schedule, ScheduleOccurrence)
from workforce.schedule_dispatch import schedule_due_once
from workforce.worker import dispatch_once


def test_scheduled_and_delegated_calls_compete_for_one_daily_cap(authenticated, monkeypatch):
    headers, project, specialist, _, manager_id = setup_manager(authenticated)
    monkeypatch.setenv('DAILY_CAP_USD', '0.000756')
    get_settings.cache_clear()
    observed = datetime.now(timezone.utc)
    price = PriceEnvelope(provider_connection='fixture-timeout', model_id='timeout-v1',
        source='synthetic-daily-budget-fixture', observed_at=observed,
        expires_at=observed + timedelta(days=1), max_input_tokens=500,
        max_output_tokens=128, input_usd_per_million=Decimal('1'),
        output_usd_per_million=Decimal('2'))
    assert price.upper_bound() == Decimal('0.000756')
    changed = authenticated.put(f'/api/agents/{specialist}/config', json={
        'expected_version': 1, 'instructions': 'Synthetic only',
        'provider_connection': 'fixture-timeout', 'model_id': 'timeout-v1',
        'price_envelope': price.model_dump(mode='json')}, headers=headers)
    assert changed.status_code == 200, changed.text
    scheduled = authenticated.post('/api/schedules', json={
        'project_id': project['id'], 'agent_id': specialist,
        'title': 'Daily priced fixture', 'timezone': 'UTC',
        'local_time': '10:00', 'root_cap': '0.5'}, headers=headers).json()
    activated = authenticated.post(f"/api/schedules/{scheduled['id']}/state", json={
        'enabled': True, 'expected_revision': 1}, headers=headers)
    assert activated.status_code == 200
    at = datetime(2030, 1, 2, 12, tzinfo=timezone.utc)
    with session_factory()() as db:
        db.get(Schedule, scheduled['id']).last_checked_at = at - timedelta(days=1)
        db.commit()
    assert schedule_due_once(at=at) == 1
    with session_factory()() as db:
        schedule_id = db.scalar(select(ScheduleOccurrence.execution_id))
    delegated = authenticated.post(f'/api/executions/{manager_id}/delegate', json={
        'request_key': 'priced-child', 'work_key': 'priced-child',
        'title': 'Priced delegated fixture', 'agent_id': specialist}, headers=headers)
    assert delegated.status_code == 202, delegated.text
    child_id = delegated.json()['id']
    DBOS(config={'name': 'workforce-test',
                 'system_database_url': 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
                 'application_version': 'usage-normalization-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 2
        statuses = [DBOS.retrieve_workflow(f'execution:{key}').get_result()
                    for key in (schedule_id, child_id)]
        assert sorted(statuses) == ['failed', 'unknown']
    finally:
        DBOS.destroy()
    with session_factory()() as db:
        today = datetime.now(timezone.utc).date()
        holds = db.scalars(select(BudgetReservation).where(
            BudgetReservation.invocation_key.in_([
                f'priced-model:{schedule_id}', f'priced-model:{child_id}']))).all()
        assert len(holds) == 1 and holds[0].status == 'unknown'
        assert holds[0].daily_day == today
        assert db.get(DailyBudgetAccount, today).reserved == Decimal('0.000756')
        assert db.get(DailyBudgetAccount, today).spent == 0
        assert db.get(BudgetAccount, holds[0].root_id).reserved == holds[0].amount
        assert db.get(Execution, child_id).root_id == manager_id
        assert db.get(BudgetAccount, child_id) is None
        assert len(db.scalars(select(ModelCall)).all()) == 1  # Manager fixture only
        # A held unknown charge belongs to its UTC day; a new day has its own cap.
        other_root = schedule_id if holds[0].root_id == manager_id else manager_id
        next_day = today + timedelta(days=1)
        next_hold = reserve_shared_cost(db, other_root, next_day, 'next-day-fixture',
                                        Decimal('0.000756'), Decimal('0.000756'))
        assert next_hold.daily_day == next_day
        assert db.get(DailyBudgetAccount, today).reserved == Decimal('0.000756')
        db.commit()
    with session_factory()() as db:
        assert settle_shared_cost(db, holds[0].invocation_key, None).status == 'unknown'
        assert db.get(DailyBudgetAccount, today).reserved == Decimal('0.000756')
