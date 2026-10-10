"""add learning-feedback session columns and per-trade fee

Revision ID: e1f2a3b4c5d6
Revises: b1c2d3e4f5a6
Create Date: 2026-10-10 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: str | Sequence[str] | None = 'b1c2d3e4f5a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Per-session, build-time-frozen learning-feedback opt-in + window.
    op.add_column(
        'paper_trading_sessions',
        sa.Column(
            'learning_feedback_enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        'paper_trading_sessions',
        sa.Column('learning_feedback_window', sa.Integer(), nullable=True),
    )
    # Per-trade transaction fee recorded at ``record_trade`` (0 for pre-existing rows).
    op.add_column(
        'paper_trades',
        sa.Column(
            'fee',
            sa.Float(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('paper_trades', 'fee')
    op.drop_column('paper_trading_sessions', 'learning_feedback_window')
    op.drop_column('paper_trading_sessions', 'learning_feedback_enabled')
