"""Add project-scoped knowledge records and source lineage.

Revision ID: f02a917b45e6
Revises: e91b0267c3d4
"""
from alembic import op
import sqlalchemy as sa

revision = 'f02a917b45e6'
down_revision = 'e91b0267c3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('memory_records',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('trust_origin', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('creator_kind', sa.String(length=30), nullable=False),
        sa.Column('creator_id', sa.String(length=36), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True)),
        sa.Column('valid_until', sa.DateTime(timezone=True)),
        sa.Column('superseded_by_id', sa.String(length=36), sa.ForeignKey('memory_records.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('fact', 'decision', 'observation', 'claim')", name='ck_memory_kind'),
        sa.CheckConstraint("trust_origin IN ('human_instruction', 'approved_decision', 'observed_result', 'external_claim', 'model_inference')", name='ck_memory_trust_origin'),
        sa.CheckConstraint("status IN ('candidate', 'active', 'superseded', 'tombstoned')", name='ck_memory_status'),
        sa.CheckConstraint('valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from', name='ck_memory_validity'))
    op.create_index('ix_memory_project_status_created', 'memory_records',
                    ['project_id', 'status', 'created_at'])
    op.create_table('memory_sources',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('record_id', sa.String(length=36), sa.ForeignKey('memory_records.id'), nullable=False),
        sa.Column('source_kind', sa.String(length=30), nullable=False),
        sa.Column('source_id', sa.String(length=36), nullable=False),
        sa.UniqueConstraint('record_id', 'source_kind', 'source_id', name='uq_memory_source_ref'),
        sa.CheckConstraint("source_kind IN ('task', 'execution', 'message', 'artifact_version', 'memory_record')", name='ck_memory_source_kind'))


def downgrade() -> None:
    op.drop_table('memory_sources')
    op.drop_index('ix_memory_project_status_created', table_name='memory_records')
    op.drop_table('memory_records')
