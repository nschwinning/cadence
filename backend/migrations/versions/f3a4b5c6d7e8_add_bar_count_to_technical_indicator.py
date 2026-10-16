"""add bar_count to technical_indicator

Revision ID: f3a4b5c6d7e8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-16 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: str | Sequence[str] | None = 'f2a3b4c5d6e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Number of daily bars a snapshot was computed from. Used to derive the
    # watchlist short-window insufficient-history marker
    # (bar_count < WATCHLIST_MIN_BARS). Nullable with no backfill: the nightly
    # run repopulates it, and pre-existing rows (NULL) are treated as
    # insufficient for watchlist reads.
    op.add_column(
        'technical_indicator',
        sa.Column('bar_count', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('technical_indicator', 'bar_count')
