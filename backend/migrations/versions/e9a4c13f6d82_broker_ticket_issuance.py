"""Fence database-bound broker ticket issuance.

Revision ID: e9a4c13f6d82
Revises: d8f3b02e5c71
"""
from alembic import op
import sqlalchemy as sa

revision = 'e9a4c13f6d82'
down_revision = 'd8f3b02e5c71'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('read_effect_attempts', sa.Column('broker_capability_hash', sa.String(64)))
    op.add_column('read_effect_attempts', sa.Column('broker_ticket_hash', sa.String(64)))
    op.add_column('read_effect_attempts', sa.Column('broker_issued_at', sa.DateTime(timezone=True)))
    op.create_check_constraint('ck_read_attempt_broker_issue', 'read_effect_attempts',
                              '(broker_ticket_hash IS NULL) = (broker_issued_at IS NULL)')
    op.create_check_constraint('ck_read_attempt_broker_capability', 'read_effect_attempts',
                              'broker_ticket_hash IS NULL OR broker_capability_hash IS NOT NULL')


def downgrade():
    op.drop_constraint('ck_read_attempt_broker_capability', 'read_effect_attempts')
    op.drop_constraint('ck_read_attempt_broker_issue', 'read_effect_attempts')
    op.drop_column('read_effect_attempts', 'broker_issued_at')
    op.drop_column('read_effect_attempts', 'broker_ticket_hash')
    op.drop_column('read_effect_attempts', 'broker_capability_hash')
