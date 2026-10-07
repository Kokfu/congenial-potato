"""Track bounded parent-child execution delegation.

Revision ID: c72f9d08b1e4
Revises: b8e4c1936a02
"""
from alembic import op
import sqlalchemy as sa

revision = 'c72f9d08b1e4'
down_revision = 'b8e4c1936a02'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('executions', sa.Column('parent_id', sa.String(length=36), nullable=True))
    op.add_column('executions', sa.Column('delegation_key', sa.String(length=100), nullable=True))
    op.add_column('executions', sa.Column('delegation_hash', sa.String(length=64), nullable=True))
    op.add_column('executions', sa.Column('depth', sa.Integer(), server_default='0', nullable=False))
    op.create_foreign_key('fk_execution_parent', 'executions', 'executions', ['parent_id'], ['id'])
    op.create_unique_constraint('uq_execution_delegation_key', 'executions',
                                ['parent_id', 'delegation_key'])


def downgrade() -> None:
    op.drop_constraint('uq_execution_delegation_key', 'executions', type_='unique')
    op.drop_constraint('fk_execution_parent', 'executions', type_='foreignkey')
    op.drop_column('executions', 'depth')
    op.drop_column('executions', 'delegation_hash')
    op.drop_column('executions', 'delegation_key')
    op.drop_column('executions', 'parent_id')
