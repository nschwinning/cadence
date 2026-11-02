"""add strategy bot tables

Revision ID: c9f1a3b7d2e4
Revises: d7a9c2e4f6b8
Create Date: 2026-11-02 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c9f1a3b7d2e4'
down_revision: str | Sequence[str] | None = 'd7a9c2e4f6b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bot_sessions',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('strategy_key', sa.Text(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column(
            'status', sa.Text(), server_default='active', nullable=False
        ),
        sa.Column(
            'benchmark', sa.Text(), server_default='SP500', nullable=False
        ),
        sa.Column(
            'initial_capital',
            sa.Float(),
            server_default='100000',
            nullable=False,
        ),
        sa.Column(
            'allocated_capital',
            sa.Float(),
            server_default='100000',
            nullable=False,
        ),
        sa.Column(
            'strategy_params',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}',
            nullable=False,
        ),
        sa.Column('take_profit_pct', sa.Float(), nullable=True),
        sa.Column('stop_loss_pct', sa.Float(), nullable=True),
        sa.Column(
            'drawdown_stop_pct',
            sa.Float(),
            server_default='0.25',
            nullable=False,
        ),
        sa.Column(
            'cash_buffer_pct', sa.Float(), server_default='0.02', nullable=False
        ),
        sa.Column(
            'peak_value', sa.Float(), server_default='100000', nullable=False
        ),
        sa.Column('position_qty', sa.Float(), nullable=True),
        sa.Column('position_avg_price', sa.Float(), nullable=True),
        sa.Column(
            'position_opened_at', sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            'total_trades', sa.Integer(), server_default='0', nullable=False
        ),
        sa.Column(
            'realised_pnl', sa.Float(), server_default='0', nullable=False
        ),
        sa.Column(
            'total_fees', sa.Float(), server_default='0', nullable=False
        ),
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
        sa.Column('last_tick_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_bot_sessions_asset', 'bot_sessions', ['asset_id'], unique=False
    )

    op.create_table(
        'bot_trades',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('bot_session_id', sa.UUID(), nullable=False),
        sa.Column('side', sa.Text(), nullable=False),
        sa.Column('ticker', sa.Text(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('filled_price', sa.Float(), nullable=True),
        sa.Column('fees', sa.Float(), server_default='0', nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('order_id', sa.Text(), nullable=True),
        sa.Column(
            'status', sa.Text(), server_default='filled', nullable=False
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['bot_session_id'], ['bot_sessions.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_bot_trades_session',
        'bot_trades',
        ['bot_session_id', 'created_at'],
        unique=False,
    )

    op.create_table(
        'bot_value_snapshots',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('bot_session_id', sa.UUID(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('realised_pnl', sa.Float(), nullable=False),
        sa.Column('unrealised_pnl', sa.Float(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['bot_session_id'], ['bot_sessions.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'bot_session_id',
            'snapshot_date',
            name='uq_bot_value_snapshots_session_date',
        ),
    )
    op.create_index(
        'idx_bot_value_snapshots_session_date',
        'bot_value_snapshots',
        ['bot_session_id', 'snapshot_date'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'idx_bot_value_snapshots_session_date',
        table_name='bot_value_snapshots',
    )
    op.drop_table('bot_value_snapshots')
    op.drop_index('idx_bot_trades_session', table_name='bot_trades')
    op.drop_table('bot_trades')
    op.drop_index('idx_bot_sessions_asset', table_name='bot_sessions')
    op.drop_table('bot_sessions')
