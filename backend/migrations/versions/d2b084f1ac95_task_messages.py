"""Persist sender-bound project task messages.

Revision ID: d2b084f1ac95
Revises: c72f9d08b1e4
"""
from alembic import op
import sqlalchemy as sa

revision = 'd2b084f1ac95'
down_revision = 'c72f9d08b1e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('task_messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('sender_execution_id', sa.String(length=36), nullable=False),
        sa.Column('sender_agent_id', sa.String(length=36), nullable=False),
        sa.Column('recipient_agent_id', sa.String(length=36), nullable=False),
        sa.Column('reply_to_id', sa.String(length=36), nullable=True),
        sa.Column('correlation_key', sa.String(length=100), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('reply_depth', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.ForeignKeyConstraint(['sender_execution_id'], ['executions.id']),
        sa.ForeignKeyConstraint(['sender_agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['recipient_agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['reply_to_id'], ['task_messages.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sender_execution_id', 'correlation_key',
                            name='uq_message_sender_correlation'))


def downgrade() -> None:
    op.drop_table('task_messages')
