"""multi-asset capital-managed bots

Convert ``bot_sessions`` from a single-asset binding (``asset_id`` + frozen
``ticker`` + three inline position columns) to a multi-asset, shared-capital-pool
model: a ``bot_symbols`` tradable set, a ``bot_positions`` open-position collection,
a persisted shared ``cash`` pool, and the ATR-sizing configuration columns. Existing
single-asset sessions are backfilled to the equivalent N=1 shape (one symbol row, one
open position row if currently held, ``sizing_method='all_in'``, ``max_positions=1``,
``max_position_pct=1.0``) so their behaviour is preserved.

Revision ID: b7d1f3a5c9e2
Revises: c9f1a3b7d2e4
Create Date: 2026-11-03 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7d1f3a5c9e2'
down_revision: str | Sequence[str] | None = 'c9f1a3b7d2e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. New session columns (shared cash pool + ATR-sizing config). Added with
    # server defaults so existing rows are valid immediately; cash is corrected
    # from the inline position below before the old columns are dropped.
    op.add_column(
        'bot_sessions',
        sa.Column(
            'cash', sa.Float(), server_default='100000', nullable=False
        ),
    )
    op.add_column(
        'bot_sessions',
        sa.Column(
            'sizing_method',
            sa.Text(),
            server_default='atr_risk',
            nullable=False,
        ),
    )
    op.add_column(
        'bot_sessions',
        sa.Column(
            'risk_pct', sa.Float(), server_default='0.01', nullable=False
        ),
    )
    op.add_column(
        'bot_sessions',
        sa.Column(
            'atr_period', sa.Integer(), server_default='14', nullable=False
        ),
    )
    op.add_column(
        'bot_sessions',
        sa.Column('atr_k', sa.Float(), server_default='2.0', nullable=False),
    )
    op.add_column(
        'bot_sessions',
        sa.Column(
            'max_position_pct',
            sa.Float(),
            server_default='0.25',
            nullable=False,
        ),
    )
    op.add_column(
        'bot_sessions',
        sa.Column(
            'max_positions', sa.Integer(), server_default='10', nullable=False
        ),
    )

    # 2. Tradable symbol set.
    op.create_table(
        'bot_symbols',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('bot_session_id', sa.UUID(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.Text(), nullable=False),
        sa.Column('alpaca_symbol', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ['bot_session_id'], ['bot_sessions.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'bot_session_id', 'asset_id', name='uq_bot_symbols_session_asset'
        ),
    )
    op.create_index(
        'idx_bot_symbols_session', 'bot_symbols', ['bot_session_id']
    )
    op.create_index(
        op.f('ix_bot_symbols_asset_id'), 'bot_symbols', ['asset_id']
    )

    # 3. Open-position collection.
    op.create_table(
        'bot_positions',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('bot_session_id', sa.UUID(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.Text(), nullable=False),
        sa.Column('alpaca_symbol', sa.Text(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('avg_price', sa.Float(), nullable=False),
        sa.Column(
            'opened_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['bot_session_id'], ['bot_sessions.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'bot_session_id', 'asset_id', name='uq_bot_positions_session_asset'
        ),
    )
    op.create_index(
        'idx_bot_positions_session', 'bot_positions', ['bot_session_id']
    )
    op.create_index(
        op.f('ix_bot_positions_asset_id'), 'bot_positions', ['asset_id']
    )

    # 4. Backfill the traded set from each session's single asset.
    op.execute(
        """
        INSERT INTO bot_symbols (bot_session_id, asset_id, ticker, alpaca_symbol)
        SELECT bs.id, bs.asset_id, bs.ticker,
               COALESCE(a.alpaca_symbol, bs.ticker)
        FROM bot_sessions bs
        JOIN assets a ON a.id = bs.asset_id
        """
    )

    # 5. Backfill an open position row for any session currently holding one.
    op.execute(
        """
        INSERT INTO bot_positions (
            bot_session_id, asset_id, ticker, alpaca_symbol,
            quantity, avg_price, opened_at
        )
        SELECT bs.id, bs.asset_id, bs.ticker,
               COALESCE(a.alpaca_symbol, bs.ticker),
               bs.position_qty, bs.position_avg_price,
               COALESCE(bs.position_opened_at, now())
        FROM bot_sessions bs
        JOIN assets a ON a.id = bs.asset_id
        WHERE bs.position_qty IS NOT NULL AND bs.position_qty > 0
        """
    )

    # 6. Correct cash from the inline position and pin legacy sizing behaviour
    # (all-in, one position, whole-budget per-name cap) so migrated bots trade
    # exactly as before.
    op.execute(
        """
        UPDATE bot_sessions
        SET cash = initial_capital
                   - COALESCE(position_qty * position_avg_price, 0),
            sizing_method = 'all_in',
            max_positions = 1,
            max_position_pct = 1.0
        """
    )

    # 7. Drop the old single-asset / inline-position columns.
    op.drop_index('idx_bot_sessions_asset', table_name='bot_sessions')
    op.drop_column('bot_sessions', 'position_opened_at')
    op.drop_column('bot_sessions', 'position_avg_price')
    op.drop_column('bot_sessions', 'position_qty')
    op.drop_column('bot_sessions', 'ticker')
    op.drop_column('bot_sessions', 'asset_id')


def downgrade() -> None:
    """Downgrade schema.

    Lossy for any true multi-symbol bot: only the first symbol (by ticker) and its
    open position, if any, are restored to the inline single-asset columns.
    """
    # 1. Restore the inline single-asset / position columns (nullable first for
    # the backfill, then asset_id/ticker tightened to NOT NULL).
    op.add_column(
        'bot_sessions', sa.Column('asset_id', sa.Integer(), nullable=True)
    )
    op.add_column('bot_sessions', sa.Column('ticker', sa.Text(), nullable=True))
    op.add_column(
        'bot_sessions', sa.Column('position_qty', sa.Float(), nullable=True)
    )
    op.add_column(
        'bot_sessions',
        sa.Column('position_avg_price', sa.Float(), nullable=True),
    )
    op.add_column(
        'bot_sessions',
        sa.Column(
            'position_opened_at', sa.DateTime(timezone=True), nullable=True
        ),
    )

    # 2. Backfill the single asset from the first symbol (by ticker) of each set.
    op.execute(
        """
        UPDATE bot_sessions bs
        SET asset_id = sym.asset_id, ticker = sym.ticker
        FROM (
            SELECT DISTINCT ON (bot_session_id)
                   bot_session_id, asset_id, ticker
            FROM bot_symbols
            ORDER BY bot_session_id, ticker
        ) sym
        WHERE sym.bot_session_id = bs.id
        """
    )

    # 3. Backfill the inline position from the first open position (by ticker).
    op.execute(
        """
        UPDATE bot_sessions bs
        SET position_qty = pos.quantity,
            position_avg_price = pos.avg_price,
            position_opened_at = pos.opened_at
        FROM (
            SELECT DISTINCT ON (bot_session_id)
                   bot_session_id, quantity, avg_price, opened_at
            FROM bot_positions
            ORDER BY bot_session_id, ticker
        ) pos
        WHERE pos.bot_session_id = bs.id
        """
    )

    op.alter_column('bot_sessions', 'asset_id', nullable=False)
    op.alter_column('bot_sessions', 'ticker', nullable=False)
    op.create_foreign_key(
        'bot_sessions_asset_id_fkey',
        'bot_sessions',
        'assets',
        ['asset_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.create_index(
        'idx_bot_sessions_asset', 'bot_sessions', ['asset_id'], unique=False
    )

    # 4. Drop the new tables and columns.
    op.drop_index(op.f('ix_bot_positions_asset_id'), table_name='bot_positions')
    op.drop_index('idx_bot_positions_session', table_name='bot_positions')
    op.drop_table('bot_positions')
    op.drop_index(op.f('ix_bot_symbols_asset_id'), table_name='bot_symbols')
    op.drop_index('idx_bot_symbols_session', table_name='bot_symbols')
    op.drop_table('bot_symbols')

    op.drop_column('bot_sessions', 'max_positions')
    op.drop_column('bot_sessions', 'max_position_pct')
    op.drop_column('bot_sessions', 'atr_k')
    op.drop_column('bot_sessions', 'atr_period')
    op.drop_column('bot_sessions', 'risk_pct')
    op.drop_column('bot_sessions', 'sizing_method')
    op.drop_column('bot_sessions', 'cash')
