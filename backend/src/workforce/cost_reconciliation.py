"""Owner attestation for uncertain synthetic model charges.

This records a decision against a held amount. It does not infer a provider
invoice or retry an uncertain external call.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .budgets import money, settle_shared_cost
from .db import db_session
from .models import AuditEvent, BudgetReservation, Execution, OwnerSession
from .security import current_session, require_csrf

router = APIRouter()


def _hold(db: Session, execution_id: str) -> BudgetReservation:
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(404, 'Execution not found')
    hold = db.scalar(select(BudgetReservation).where(
        BudgetReservation.invocation_key == f'priced-model:{execution_id}'))
    if hold is None or hold.root_id != execution.root_id or hold.daily_day is None:
        raise HTTPException(404, 'Priced model hold not found')
    return hold


@router.get('/api/executions/{execution_id}/cost-hold')
def get_cost_hold(execution_id: str, _: OwnerSession = Depends(current_session),
                  db: Session = Depends(db_session)):
    hold = _hold(db, execution_id)
    return {'execution_id': execution_id, 'amount': hold.amount, 'status': hold.status,
            'actual': hold.actual, 'utc_day': hold.daily_day}


class SyntheticReconciliation(BaseModel):
    expected_hold_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=6)
    charged_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=6)
    evidence_reference: str = Field(pattern=r'^synthetic:[A-Za-z0-9._:/-]{1,120}$')


@router.post('/api/executions/{execution_id}/cost-reconciliation')
def reconcile_synthetic_cost(execution_id: str, data: SyntheticReconciliation,
                             session: OwnerSession = Depends(require_csrf),
                             db: Session = Depends(db_session)):
    hold = _hold(db, execution_id)
    if hold.amount != money(data.expected_hold_amount):
        raise HTTPException(409, 'Cost hold amount changed')
    if hold.status not in ('unknown', 'settled', 'settled_overrun'):
        raise HTTPException(409, 'Cost outcome is not ready for reconciliation')
    initial_status = hold.status
    effect_key = f'cost-reconcile:{execution_id}'
    try:
        settled = settle_shared_cost(db, hold.invocation_key, data.charged_usd)
    except ValueError as exc:
        raise HTTPException(409, 'Cost charge conflicts with recorded settlement') from exc
    prior = db.scalar(select(AuditEvent).where(AuditEvent.effect_key == effect_key))
    detail = {'hold_id': hold.id, 'expected_hold_amount': str(hold.amount),
              'charged_usd': str(money(data.charged_usd)),
              'evidence_reference': data.evidence_reference, 'synthetic_only': True}
    if prior is not None:
        if prior.detail != detail:
            raise HTTPException(409, 'Cost reconciliation evidence changed')
    elif initial_status != 'unknown':
        raise HTTPException(409, 'Prior cost settlement has no reconciliation evidence')
    else:
        db.add(AuditEvent(actor=session.owner_id, action='cost.reconcile', resource=execution_id,
                          outcome=settled.status, detail=detail, effect_key=effect_key))
    db.commit()
    return {'execution_id': execution_id, 'status': settled.status, 'charged_usd': settled.actual,
            'evidence_reference': data.evidence_reference}
