"""bot orchestrator

Revision ID: dccd2472daa2
Revises: 7dbcea076d4b
Create Date: 2026-11-10 08:28:13.520277

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dccd2472daa2'
down_revision: str | Sequence[str] | None = '7dbcea076d4b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_BOT_SESSION_ORCHESTRATOR = 'fk_bot_sessions_orchestrator_id'


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bot_orchestrators',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default='active', nullable=False),
        sa.Column('capital', sa.Float(), nullable=False),
        sa.Column('free_capital', sa.Float(), nullable=False),
        sa.Column('max_parallel_bots', sa.Integer(), nullable=False),
        sa.Column('max_bot_share', sa.Float(), nullable=False),
        sa.Column('max_tickers_per_bot', sa.Integer(), nullable=False),
        sa.Column('cadence', sa.Text(), nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('benchmark', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('stopped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'bot_orchestrator_runs',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('orchestrator_id', sa.UUID(), nullable=False),
        sa.Column('trigger', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default='queued', nullable=False),
        sa.Column('prompt_version', sa.Integer(), nullable=True),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('briefing', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('decision', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('applied', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rejected', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('research', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['orchestrator_id'], ['bot_orchestrators.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_orchestrator_runs_created',
        'bot_orchestrator_runs',
        ['orchestrator_id', 'created_at'],
        unique=False,
    )
    # At most one queued-or-running run per orchestrator.
    op.create_index(
        'uq_orchestrator_live_run',
        'bot_orchestrator_runs',
        ['orchestrator_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.add_column(
        'bot_sessions', sa.Column('orchestrator_id', sa.UUID(), nullable=True)
    )
    op.add_column(
        'bot_sessions',
        sa.Column('capital_returned_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f('ix_bot_sessions_orchestrator_id'),
        'bot_sessions',
        ['orchestrator_id'],
        unique=False,
    )
    op.create_foreign_key(
        _FK_BOT_SESSION_ORCHESTRATOR,
        'bot_sessions',
        'bot_orchestrators',
        ['orchestrator_id'],
        ['id'],
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        _FK_BOT_SESSION_ORCHESTRATOR, 'bot_sessions', type_='foreignkey'
    )
    op.drop_index(op.f('ix_bot_sessions_orchestrator_id'), table_name='bot_sessions')
    op.drop_column('bot_sessions', 'capital_returned_at')
    op.drop_column('bot_sessions', 'orchestrator_id')
    op.drop_index(
        'uq_orchestrator_live_run',
        table_name='bot_orchestrator_runs',
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.drop_index('idx_orchestrator_runs_created', table_name='bot_orchestrator_runs')
    op.drop_table('bot_orchestrator_runs')
    op.drop_table('bot_orchestrators')
