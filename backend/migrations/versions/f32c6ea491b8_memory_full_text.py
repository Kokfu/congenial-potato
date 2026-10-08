"""Index project memory content for bounded lexical search.

Revision ID: f32c6ea491b8
Revises: f22b839c56a7
"""
from alembic import op
import sqlalchemy as sa

revision = 'f32c6ea491b8'
down_revision = 'f22b839c56a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('memory_records', sa.Column('search_vector',
        sa.dialects.postgresql.TSVECTOR(),
        sa.Computed("to_tsvector('english', content)", persisted=True)))
    op.create_index('ix_memory_content_fts', 'memory_records', ['search_vector'],
                    postgresql_using='gin')


def downgrade() -> None:
    op.drop_index('ix_memory_content_fts', table_name='memory_records')
    op.drop_column('memory_records', 'search_vector')
