"""Fence isolated mediated reads before dispatch.

Revision ID: d8f3b02e5c71
Revises: c7e2a91d4b60
"""
from alembic import op
import sqlalchemy as sa

revision = 'd8f3b02e5c71'
down_revision = 'c7e2a91d4b60'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('read_effect_attempts',
        sa.Column('invocation_id', sa.String(36), sa.ForeignKey('tool_invocations.id'), primary_key=True),
        sa.Column('approval_id', sa.String(36), sa.ForeignKey('approvals.id'), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('root_id', sa.String(36), sa.ForeignKey('executions.id'), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('reason', sa.String(120)),
        sa.Column('observation_id', sa.String(36), sa.ForeignKey('external_read_observations.id'), unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('unknown', 'succeeded', 'discarded')", name='ck_read_attempt_status'),
        sa.CheckConstraint("(status = 'succeeded') = (observation_id IS NOT NULL)", name='ck_read_attempt_observation'))


def downgrade():
    op.drop_table('read_effect_attempts')
