"""Link exact approval waits to one tool invocation.

Revision ID: f72a0d46b931
Revises: f62a9d017c3b
"""
from alembic import op
import sqlalchemy as sa

revision = 'f72a0d46b931'
down_revision = 'f62a9d017c3b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('approvals', sa.Column('tool_invocation_id', sa.String(36)))
    op.create_foreign_key('fk_approval_tool_invocation', 'approvals', 'tool_invocations',
                          ['tool_invocation_id'], ['id'])
    op.create_unique_constraint('uq_approval_tool_invocation', 'approvals',
                                ['tool_invocation_id'])


def downgrade() -> None:
    op.drop_constraint('uq_approval_tool_invocation', 'approvals', type_='unique')
    op.drop_constraint('fk_approval_tool_invocation', 'approvals', type_='foreignkey')
    op.drop_column('approvals', 'tool_invocation_id')
