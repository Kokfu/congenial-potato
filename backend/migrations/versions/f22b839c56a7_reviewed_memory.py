"""Bind memory candidates to owner review and record acknowledged conflicts.

Revision ID: f22b839c56a7
Revises: f02a917b45e6
"""
from alembic import op
import sqlalchemy as sa

revision = 'f22b839c56a7'
down_revision = 'f02a917b45e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('memory_records', sa.Column('subject_key', sa.String(100), nullable=False,
                                               server_default=''))
    op.add_column('memory_records', sa.Column('payload_hash', sa.String(64), nullable=False,
                                               server_default=''))
    op.add_column('memory_records', sa.Column('reviewed_by_id', sa.String(36)))
    op.add_column('memory_records', sa.Column('reviewed_at', sa.DateTime(timezone=True)))
    op.add_column('memory_records', sa.Column('source_execution_id', sa.String(36)))
    op.create_foreign_key('fk_memory_source_execution', 'memory_records', 'executions',
                          ['source_execution_id'], ['id'])
    op.create_unique_constraint('uq_memory_source_execution', 'memory_records', ['source_execution_id'])
    op.create_foreign_key('fk_memory_reviewed_by', 'memory_records', 'owners',
                          ['reviewed_by_id'], ['id'])
    op.drop_constraint('ck_memory_status', 'memory_records', type_='check')
    op.create_check_constraint('ck_memory_status', 'memory_records',
        "status IN ('candidate', 'active', 'rejected', 'invalidated', 'superseded', 'tombstoned')")
    op.create_table('memory_conflicts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('record_id', sa.String(36), sa.ForeignKey('memory_records.id'), nullable=False),
        sa.Column('other_record_id', sa.String(36), sa.ForeignKey('memory_records.id'), nullable=False),
        sa.Column('acknowledged_by_id', sa.String(36), sa.ForeignKey('owners.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('record_id', 'other_record_id', name='uq_memory_conflict_pair'),
        sa.CheckConstraint('record_id <> other_record_id', name='ck_memory_conflict_distinct'))


def downgrade() -> None:
    op.drop_table('memory_conflicts')
    op.drop_constraint('ck_memory_status', 'memory_records', type_='check')
    op.create_check_constraint('ck_memory_status', 'memory_records',
        "status IN ('candidate', 'active', 'superseded', 'tombstoned')")
    op.drop_constraint('fk_memory_reviewed_by', 'memory_records', type_='foreignkey')
    op.drop_column('memory_records', 'reviewed_at')
    op.drop_constraint('uq_memory_source_execution', 'memory_records', type_='unique')
    op.drop_constraint('fk_memory_source_execution', 'memory_records', type_='foreignkey')
    op.drop_column('memory_records', 'source_execution_id')
    op.drop_column('memory_records', 'reviewed_by_id')
    op.drop_column('memory_records', 'payload_hash')
    op.drop_column('memory_records', 'subject_key')
