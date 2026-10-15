"""Independent single-use runner admission. No result or product dispatch.

Revision ID: b942d5e8f163
Revises: a831c4d7e052
"""
from alembic import op
import sqlalchemy as sa

revision = 'b942d5e8f163'
down_revision = 'a831c4d7e052'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('runner_attempts',
        sa.Column('invocation_id', sa.String(36), sa.ForeignKey('tool_invocations.id'), primary_key=True),
        sa.Column('approval_id', sa.String(36), sa.ForeignKey('approvals.id'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('root_id', sa.String(36), sa.ForeignKey('executions.id'), nullable=False),
        sa.Column('binding_hash', sa.String(64), nullable=False),
        sa.Column('manifest_sha256', sa.String(64), nullable=False),
        sa.Column('capability_hash', sa.String(64), nullable=False),
        sa.Column('image_id', sa.String(71), nullable=False),
        sa.Column('job_sha256', sa.String(64), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('reason', sa.String(120)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'unknown'", name='ck_runner_attempt_status'),
        sa.CheckConstraint('expires_at > issued_at', name='ck_runner_attempt_expiry'))


def downgrade() -> None:
    if op.get_bind().execute(sa.text('SELECT 1 FROM runner_attempts LIMIT 1')).first():
        raise RuntimeError('Cannot erase consumed runner admissions')
    op.drop_table('runner_attempts')
