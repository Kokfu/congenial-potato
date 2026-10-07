"""Persist exact approval payloads.

Revision ID: a1d387ca2e90
Revises: f1ada22d1e47
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1d387ca2e90'
down_revision = 'f1ada22d1e47'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('approvals', sa.Column('payload', sa.JSON(), nullable=True))
    op.add_column('approvals', sa.Column('decision_payload_hash', sa.String(length=64), nullable=True))
    op.execute("UPDATE approvals SET payload = '{}'::json WHERE payload IS NULL")
    op.alter_column('approvals', 'payload', nullable=False)


def downgrade() -> None:
    op.drop_column('approvals', 'decision_payload_hash')
    op.drop_column('approvals', 'payload')
