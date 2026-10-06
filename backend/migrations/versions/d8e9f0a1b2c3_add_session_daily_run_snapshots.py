"""add session_daily_run_snapshots

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-05 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd8e9f0a1b2c3'
down_revision: str | Sequence[str] | None = 'c7d8e9f0a1b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'session_daily_run_snapshots',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=True),
        sa.Column('portfolio_id', sa.UUID(), nullable=True),
        sa.Column('run_date', sa.Date(), nullable=False),
        sa.Column('ai_portfolio_event_id', sa.UUID(), nullable=True),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(
            ['session_id'], ['paper_trading_sessions.id'], ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['portfolio_id'], ['portfolios.id'], ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['ai_portfolio_event_id'], ['ai_portfolio_events.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'session_id', 'run_date', name='uq_session_daily_run_snapshots_session_date'
        ),
    )
    op.create_index(
        'idx_session_daily_run_snapshots_session_date',
        'session_daily_run_snapshots',
        ['session_id', 'run_date'],
        unique=False,
    )
    op.create_index(
        'idx_session_daily_run_snapshots_portfolio',
        'session_daily_run_snapshots',
        ['portfolio_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'idx_session_daily_run_snapshots_portfolio',
        table_name='session_daily_run_snapshots',
    )
    op.drop_index(
        'idx_session_daily_run_snapshots_session_date',
        table_name='session_daily_run_snapshots',
    )
    op.drop_table('session_daily_run_snapshots')
