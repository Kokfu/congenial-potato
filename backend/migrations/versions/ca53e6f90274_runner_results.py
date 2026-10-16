"""Accept exact synthetic runner metadata without product dispatch.

Revision ID: ca53e6f90274
Revises: b942d5e8f163
"""
from alembic import op
import sqlalchemy as sa

revision = 'ca53e6f90274'
down_revision = 'b942d5e8f163'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('runner_attempts', sa.Column('accepted_result_hash', sa.String(64)))
    op.drop_constraint('ck_runner_attempt_status', 'runner_attempts', type_='check')
    op.create_check_constraint('ck_runner_attempt_status', 'runner_attempts', "status IN ('unknown', 'accepted')")
    op.create_check_constraint('ck_runner_attempt_result', 'runner_attempts',
                               "(status = 'accepted') = (accepted_result_hash IS NOT NULL)")
    op.create_table('runner_results',
        sa.Column('invocation_id', sa.String(36), sa.ForeignKey('runner_attempts.invocation_id'), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('root_id', sa.String(36), sa.ForeignKey('executions.id'), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('trust_origin', sa.String(30), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("trust_origin = 'synthetic_runner'", name='ck_runner_result_trust'))


def downgrade() -> None:
    bind = op.get_bind()
    if (bind.execute(sa.text('SELECT 1 FROM runner_results LIMIT 1')).first() or
            bind.execute(sa.text("SELECT 1 FROM runner_attempts WHERE status = 'accepted' LIMIT 1")).first()):
        raise RuntimeError('Cannot erase accepted runner results')
    op.drop_table('runner_results')
    op.drop_constraint('ck_runner_attempt_result', 'runner_attempts', type_='check')
    op.drop_constraint('ck_runner_attempt_status', 'runner_attempts', type_='check')
    op.create_check_constraint('ck_runner_attempt_status', 'runner_attempts', "status = 'unknown'")
    op.drop_column('runner_attempts', 'accepted_result_hash')
