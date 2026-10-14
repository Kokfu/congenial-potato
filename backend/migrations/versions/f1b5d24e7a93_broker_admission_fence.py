"""Fence mediator admission independently of the broker journal.

Revision ID: f1b5d24e7a93
Revises: e9a4c13f6d82
"""
from alembic import op
import sqlalchemy as sa

revision = 'f1b5d24e7a93'
down_revision = 'e9a4c13f6d82'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('read_effect_attempts', sa.Column('broker_permit_consumed', sa.Boolean(),
                                                 nullable=False, server_default=sa.false()))
    # Existing issued tickets may already have fetched. Fence all of them,
    # including an issued ticket whose actual dispatch was never confirmed.
    # This flag is uncertainty/admission state, not an invented fetch timestamp.
    op.execute('UPDATE read_effect_attempts SET broker_permit_consumed = true '
               'WHERE broker_ticket_hash IS NOT NULL')
    op.create_check_constraint('ck_read_attempt_broker_admission', 'read_effect_attempts',
                              'NOT broker_permit_consumed OR broker_ticket_hash IS NOT NULL')


def downgrade():
    op.drop_constraint('ck_read_attempt_broker_admission', 'read_effect_attempts')
    op.drop_column('read_effect_attempts', 'broker_permit_consumed')
