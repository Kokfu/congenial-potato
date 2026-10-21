"""Bind explicitly requested synthetic drafts to exact reviewed plans."""
from alembic import op
import sqlalchemy as sa

revision = 'f0d2f573e406'
down_revision = 'e9c1e462d3f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('document_draft_runs',
        sa.Column('execution_id', sa.String(36), sa.ForeignKey('executions.id'), primary_key=True),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('plan_proposals.id'), nullable=False),
        sa.Column('plan_digest', sa.String(64), nullable=False))


def downgrade() -> None:
    if op.get_bind().execute(sa.text('SELECT 1 FROM document_draft_runs LIMIT 1')).first():
        raise RuntimeError('Cannot erase reviewed document draft history')
    op.drop_table('document_draft_runs')
