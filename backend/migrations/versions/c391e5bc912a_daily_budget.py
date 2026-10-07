"""Add a shared UTC daily cost ledger.

Revision ID: c391e5bc912a
Revises: b289c6e2c9bf
"""
from alembic import op
import sqlalchemy as sa

revision = 'c391e5bc912a'
down_revision = 'b289c6e2c9bf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('daily_budget_accounts',
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('cap', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('reserved', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('spent', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.PrimaryKeyConstraint('day'))
    op.add_column('budget_reservations', sa.Column('daily_day', sa.Date(), nullable=True))
    op.add_column('budget_reservations', sa.Column('actual', sa.Numeric(precision=18, scale=6), nullable=True))
    op.create_foreign_key('fk_budget_reservations_daily_day', 'budget_reservations',
                          'daily_budget_accounts', ['daily_day'], ['day'])


def downgrade() -> None:
    op.drop_constraint('fk_budget_reservations_daily_day', 'budget_reservations', type_='foreignkey')
    op.drop_column('budget_reservations', 'actual')
    op.drop_column('budget_reservations', 'daily_day')
    op.drop_table('daily_budget_accounts')
