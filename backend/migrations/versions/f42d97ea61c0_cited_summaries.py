"""Add immutable, cited project summary versions.

Revision ID: f42d97ea61c0
Revises: f32c6ea491b8
"""
from alembic import op
import sqlalchemy as sa

revision = 'f42d97ea61c0'
down_revision = 'f32c6ea491b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('project_summary_versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.String(36), sa.ForeignKey('project_summary_versions.id')),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('author_id', sa.String(36), sa.ForeignKey('owners.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'version', name='uq_project_summary_version'))
    op.create_table('project_summary_citations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('summary_id', sa.String(36), sa.ForeignKey('project_summary_versions.id'), nullable=False),
        sa.Column('record_id', sa.String(36), sa.ForeignKey('memory_records.id'), nullable=False),
        sa.UniqueConstraint('summary_id', 'record_id', name='uq_project_summary_citation'))


def downgrade() -> None:
    op.drop_table('project_summary_citations')
    op.drop_table('project_summary_versions')
