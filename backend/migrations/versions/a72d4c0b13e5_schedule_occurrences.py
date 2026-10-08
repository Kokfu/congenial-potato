"""Add durable daily occurrence ledger and cursor.

Revision ID: a72d4c0b13e5
Revises: a62c3d9f0b14
"""
from alembic import op
import sqlalchemy as sa

revision = 'a72d4c0b13e5'
down_revision = 'a62c3d9f0b14'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('schedules', sa.Column('last_checked_at',
                                        sa.DateTime(timezone=True), nullable=True))
    op.create_table('schedule_occurrences',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('schedule_id', sa.String(36), sa.ForeignKey('schedules.id'), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('local_date', sa.Date(), nullable=False),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('reason', sa.String(100), nullable=True),
        sa.Column('execution_id', sa.String(36), sa.ForeignKey('executions.id'),
                  unique=True, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('schedule_id', 'local_date', name='uq_schedule_occurrence_day'))


def downgrade() -> None:
    op.drop_table('schedule_occurrences')
    op.drop_column('schedules', 'last_checked_at')
