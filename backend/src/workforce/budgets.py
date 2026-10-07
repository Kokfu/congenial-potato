"""Conservative root/daily money holds for future governed provider calls."""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_UP

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import BudgetAccount, BudgetReservation, DailyBudgetAccount
from .services import AccessDenied

CENT_MICRO = Decimal('0.000001')


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT_MICRO, rounding=ROUND_UP)


class PriceEnvelope(BaseModel):
    """Operator-validated upper prices; provider listings do not create these."""
    provider_connection: str
    model_id: str
    source: str = Field(min_length=1)
    observed_at: datetime
    expires_at: datetime
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    input_usd_per_million: Decimal = Field(ge=0)
    output_usd_per_million: Decimal = Field(ge=0)

    def upper_bound(self) -> Decimal:
        if self.expires_at.tzinfo is None or self.expires_at <= datetime.now(timezone.utc):
            raise AccessDenied('Price envelope expired')
        estimate = (self.max_input_tokens * self.input_usd_per_million +
                    self.max_output_tokens * self.output_usd_per_million) / Decimal(1_000_000)
        if estimate <= 0:
            raise AccessDenied('Price upper bound is unavailable')
        return money(estimate)

    def actual_cost(self, input_tokens: int | None, output_tokens: int | None) -> Decimal | None:
        if input_tokens is None or output_tokens is None:
            return None
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError('Reported usage cannot be negative')
        return money((input_tokens * self.input_usd_per_million +
                      output_tokens * self.output_usd_per_million) / Decimal(1_000_000))


def reserve_shared_cost(db: Session, root_id: str, day: date, key: str,
                        upper_bound: Decimal, daily_cap: Decimal) -> BudgetReservation:
    """Lock the shared UTC day first, then the root for a consistent order."""
    if upper_bound <= 0 or daily_cap <= 0:
        raise ValueError('Cost hold and daily cap must be positive')
    amount = money(upper_bound)
    existing = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == key))
    if existing and (existing.root_id != root_id or existing.daily_day != day or existing.amount != amount):
        raise ValueError('Idempotency key reused for a different cost hold')
    db.execute(insert(DailyBudgetAccount).values(day=day, cap=daily_cap,
               reserved=Decimal(0), spent=Decimal(0), currency='USD').on_conflict_do_nothing(index_elements=['day']))
    daily = db.execute(select(DailyBudgetAccount).where(DailyBudgetAccount.day == day).with_for_update()).scalar_one()
    root = db.execute(select(BudgetAccount).where(BudgetAccount.root_id == root_id).with_for_update()).scalar_one_or_none()
    if root is None:
        raise AccessDenied('Root budget unavailable')
    if root.currency != 'USD' or daily.currency != 'USD' or daily.cap != daily_cap:
        raise AccessDenied('Budget currency or configured daily cap changed')
    existing = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == key))
    if existing:
        if existing.root_id != root_id or existing.daily_day != day or existing.amount != amount:
            raise ValueError('Idempotency key reused for a different cost hold')
        return existing
    if root.cap - root.spent - root.reserved < amount or daily.cap - daily.spent - daily.reserved < amount:
        raise AccessDenied('Root or daily budget exhausted')
    root.reserved += amount
    daily.reserved += amount
    reservation = BudgetReservation(root_id=root_id, invocation_key=key, amount=amount, daily_day=day)
    db.add(reservation)
    db.flush()
    return reservation


def settle_shared_cost(db: Session, key: str, actual: Decimal | None) -> BudgetReservation:
    """Unknown outcomes retain the hold until explicit reconciliation."""
    initial = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == key))
    if initial is None or initial.daily_day is None:
        raise ValueError('Shared cost hold not found')
    daily = db.execute(select(DailyBudgetAccount).where(DailyBudgetAccount.day == initial.daily_day).with_for_update()).scalar_one()
    root = db.execute(select(BudgetAccount).where(BudgetAccount.root_id == initial.root_id).with_for_update()).scalar_one()
    hold = db.execute(select(BudgetReservation).where(BudgetReservation.id == initial.id).with_for_update()).scalar_one()
    if hold.status in ('settled', 'settled_overrun'):
        if actual is None or hold.actual != money(actual):
            raise ValueError('Cost settlement changed after recording')
        return hold
    if hold.status not in ('reserved', 'unknown'):
        raise ValueError('Cost hold is not open')
    if actual is None:
        hold.status = 'unknown'
        return hold
    if actual < 0:
        raise ValueError('Actual cost cannot be negative')
    charged = money(actual)
    root.reserved -= hold.amount
    daily.reserved -= hold.amount
    root.spent += charged
    daily.spent += charged
    hold.actual = charged
    hold.status = 'settled_overrun' if charged > hold.amount else 'settled'
    return hold
