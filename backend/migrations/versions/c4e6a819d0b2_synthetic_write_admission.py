"""Pin one synthetic-write ledger and consume exact target revisions."""
from alembic import op
import sqlalchemy as sa

revision = 'c4e6a819d0b2'
down_revision = 'ca53e6f90274'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('synthetic_write_ledger_control',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ledger_id', sa.String(36), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_check_constraint('ck_synthetic_write_ledger_control_singleton',
        'synthetic_write_ledger_control', 'id = 1')
    op.create_table('synthetic_write_admissions',
        sa.Column('invocation_id', sa.String(36),
            sa.ForeignKey('tool_invocations.id'), primary_key=True),
        sa.Column('approval_id', sa.String(36), sa.ForeignKey('approvals.id'), nullable=False),
        sa.Column('ledger_id', sa.String(36),
            sa.ForeignKey('synthetic_write_ledger_control.ledger_id'), nullable=False),
        sa.Column('record_id', sa.String(36), nullable=False),
        sa.Column('expected_revision', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('root_id', sa.String(36), sa.ForeignKey('executions.id'), nullable=False),
        sa.Column('approval_payload_sha256', sa.String(64), nullable=False),
        sa.Column('policy_snapshot_sha256', sa.String(64), nullable=False),
        sa.Column('intent_sha256', sa.String(64), nullable=False),
        sa.Column('capability_sha256', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'unknown'", name='ck_synthetic_write_admission_status'),
        sa.CheckConstraint('expected_revision BETWEEN 0 AND 2147483646',
            name='ck_synthetic_write_expected_revision'),
        sa.UniqueConstraint('ledger_id', 'record_id', 'expected_revision',
            name='uq_synthetic_write_target_revision'))


def downgrade() -> None:
    bind = op.get_bind()
    if (bind.execute(sa.text('SELECT 1 FROM synthetic_write_admissions LIMIT 1')).first() or
            bind.execute(sa.text('SELECT 1 FROM synthetic_write_ledger_control LIMIT 1')).first()):
        raise RuntimeError('Cannot erase consumed synthetic write admission or ledger identity')
    op.drop_table('synthetic_write_admissions')
    op.drop_table('synthetic_write_ledger_control')
