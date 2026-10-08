"""Store immutable, project-scoped external read observations.

Revision ID: b0d7e32a4c19
Revises: a9e3f40c2d16
"""
from alembic import op
import sqlalchemy as sa

revision = 'b0d7e32a4c19'
down_revision = 'a9e3f40c2d16'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('external_read_observations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('invocation_key', sa.String(160), unique=True, nullable=False),
        sa.Column('source_url', sa.String(2048), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('media_type', sa.String(100), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('trust_origin', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("trust_origin = 'external_claim'", name='ck_external_read_trust'),
        sa.CheckConstraint('size BETWEEN 0 AND 65536', name='ck_external_read_size'))
    op.create_index('ix_external_read_project_time', 'external_read_observations',
                    ['project_id', 'retrieved_at'])


def downgrade() -> None:
    op.drop_index('ix_external_read_project_time', table_name='external_read_observations')
    op.drop_table('external_read_observations')
