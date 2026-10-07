from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from workforce.budgets import PriceEnvelope, reserve_shared_cost, settle_shared_cost
from workforce.db import session_factory
from workforce.models import BudgetAccount, BudgetReservation, DailyBudgetAccount
from workforce.services import AccessDenied

DAY = date(2026, 10, 7)


def root(cap: str = '1.000000') -> str:
    key = str(uuid4())
    with session_factory()() as db:
        db.add(BudgetAccount(root_id=key, cap=Decimal(cap), reserved=Decimal(0), spent=Decimal(0)))
        db.commit()
    return key


def test_concurrent_roots_cannot_oversubscribe_one_daily_cap():
    roots = [root(), root()]

    def attempt(index):
        with session_factory()() as db:
            try:
                reserve_shared_cost(db, roots[index], DAY, f'child:{index}', Decimal('0.7'), Decimal('1.0'))
                db.commit()
                return 'reserved'
            except AccessDenied:
                db.rollback()
                return 'denied'

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ['denied', 'reserved']
    with session_factory()() as db:
        assert db.get(DailyBudgetAccount, DAY).reserved == Decimal('0.700000')


def test_duplicate_key_and_unknown_outcome_reconciliation():
    root_id = root()

    def reserve():
        with session_factory()() as db:
            hold = reserve_shared_cost(db, root_id, DAY, 'same-logical-call', Decimal('0.7'), Decimal('1.0'))
            db.commit()
            return hold.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: reserve(), range(2)))
    assert ids[0] == ids[1]
    with session_factory()() as db:
        assert settle_shared_cost(db, 'same-logical-call', None).status == 'unknown'
        db.commit()
    with session_factory()() as db:
        assert db.get(DailyBudgetAccount, DAY).reserved == Decimal('0.700000')
        hold = settle_shared_cost(db, 'same-logical-call', Decimal('0.5'))
        assert hold.status == 'settled' and hold.actual == Decimal('0.500000')
        db.commit()
    with session_factory()() as db:
        assert settle_shared_cost(db, 'same-logical-call', Decimal('0.5')).id == ids[0]
        with pytest.raises(ValueError, match='changed'):
            settle_shared_cost(db, 'same-logical-call', Decimal('0.6'))
        assert db.get(BudgetAccount, root_id).reserved == 0
        assert db.get(BudgetAccount, root_id).spent == Decimal('0.500000')
        assert db.get(DailyBudgetAccount, DAY).spent == Decimal('0.500000')
        assert len(db.scalars(select(BudgetReservation)).all()) == 1


def test_overrun_is_recorded_and_blocks_new_holds():
    first, second = root(cap='2.0'), root(cap='2.0')
    with session_factory()() as db:
        reserve_shared_cost(db, first, DAY, 'overrun', Decimal('0.7'), Decimal('1.0'))
        db.commit()
    with session_factory()() as db:
        assert settle_shared_cost(db, 'overrun', Decimal('1.2')).status == 'settled_overrun'
        db.commit()
    with session_factory()() as db:
        assert db.get(DailyBudgetAccount, DAY).spent == Decimal('1.200000')
        with pytest.raises(AccessDenied, match='exhausted'):
            reserve_shared_cost(db, second, DAY, 'another', Decimal('0.1'), Decimal('1.0'))


def test_price_envelope_requires_fresh_upper_bound_and_unknown_usage():
    observed = datetime.now(timezone.utc)
    price = PriceEnvelope(provider_connection='offline-fixture', model_id='operator-validated',
                          source='synthetic operator manifest', observed_at=observed,
                          expires_at=observed + timedelta(days=1), max_input_tokens=1000,
                          max_output_tokens=500, input_usd_per_million=Decimal('2'),
                          output_usd_per_million=Decimal('10'))
    assert price.upper_bound() == Decimal('0.007000')
    assert price.actual_cost(200, 100) == Decimal('0.001400')
    assert price.actual_cost(None, 100) is None
    with pytest.raises(AccessDenied, match='expired'):
        price.model_copy(update={'expires_at': observed - timedelta(seconds=1)}).upper_bound()
