from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import AgentProjectGrant, BudgetAccount, BudgetReservation


class AccessDenied(Exception):
    pass


def authorize_agent_project(db: Session, agent_id: str, project_id: str, action: str) -> None:
    grants = db.scalars(select(AgentProjectGrant).where(
        AgentProjectGrant.agent_id == agent_id,
        AgentProjectGrant.project_id == project_id,
        AgentProjectGrant.action == action,
    ).with_for_update()).all()
    if not grants or any(not grant.allowed for grant in grants):
        raise AccessDenied('Project access denied')


def reserve_budget(db: Session, root_id: str, invocation_key: str, amount: Decimal) -> BudgetReservation:
    if amount <= 0:
        raise ValueError('Reservation must be positive')
    account = db.execute(select(BudgetAccount).where(BudgetAccount.root_id == root_id).with_for_update()).scalar_one_or_none()
    if account is None:
        raise AccessDenied('Root budget unavailable')
    existing = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == invocation_key))
    if existing:
        if existing.root_id != root_id or existing.amount != amount:
            raise ValueError('Idempotency key reused with different reservation')
        return existing
    if account.cap - account.spent - account.reserved < amount:
        raise AccessDenied('Root budget exhausted')
    account.reserved += amount
    reservation = BudgetReservation(root_id=root_id, invocation_key=invocation_key, amount=amount)
    db.add(reservation)
    db.flush()
    return reservation
