"""Retain source-bound plan/task association without enabling draft dispatch."""
from alembic import op
import sqlalchemy as sa

revision = 'e9c1e462d3f5'
down_revision = 'e8b0d351c2e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('document_plan_tasks',
        sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id'), primary_key=True),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('plan_proposals.id'), nullable=False))


def downgrade() -> None:
    if op.get_bind().execute(sa.text('SELECT 1 FROM document_plan_tasks LIMIT 1')).first():
        raise RuntimeError('Cannot erase source-bound plan task history')
    op.drop_table('document_plan_tasks')
