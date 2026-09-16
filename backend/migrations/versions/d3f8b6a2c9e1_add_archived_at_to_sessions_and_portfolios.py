"""add archived_at to paper_trading_sessions and portfolios

Revision ID: d3f8b6a2c9e1
Revises: a2c5e8d4f1b7
Create Date: 2026-09-16 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3f8b6a2c9e1'
down_revision: str | Sequence[str] | None = 'a2c5e8d4f1b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'paper_trading_sessions',
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f('ix_paper_trading_sessions_archived_at'),
        'paper_trading_sessions',
        ['archived_at'],
        unique=False,
    )
    op.add_column(
        'portfolios',
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f('ix_portfolios_archived_at'),
        'portfolios',
        ['archived_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_portfolios_archived_at'), table_name='portfolios'
    )
    op.drop_column('portfolios', 'archived_at')
    op.drop_index(
        op.f('ix_paper_trading_sessions_archived_at'),
        table_name='paper_trading_sessions',
    )
    op.drop_column('paper_trading_sessions', 'archived_at')
