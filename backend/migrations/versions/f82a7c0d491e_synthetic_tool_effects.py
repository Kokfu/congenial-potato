"""Add an isolated idempotency ledger for fake tool effects.

Revision ID: f82a7c0d491e
Revises: f72a0d46b931
"""
from alembic import op
import sqlalchemy as sa

revision = 'f82a7c0d491e'
down_revision = 'f72a0d46b931'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('synthetic_tool_effects',
        sa.Column('invocation_key', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('action', sa.String(120), nullable=False),
        sa.Column('argument_hash', sa.String(64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table('synthetic_tool_effects')
