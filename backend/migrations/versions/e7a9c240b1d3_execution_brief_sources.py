"""Pin sources for newly admitted runs; never guess historical run context."""
from alembic import op
import sqlalchemy as sa

revision = 'e7a9c240b1d3'
down_revision = 'e6b8d130a9f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('execution_brief_sources',
        sa.Column('execution_id', sa.String(36), sa.ForeignKey('executions.id'), primary_key=True),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(['project_id', 'revision'],
            ['project_brief_versions.project_id', 'project_brief_versions.revision']))


def downgrade() -> None:
    if op.get_bind().execute(sa.text('SELECT 1 FROM execution_brief_sources LIMIT 1')).first():
        raise RuntimeError('Cannot erase recorded execution brief sources')
    op.drop_table('execution_brief_sources')
