"""add use_technical_indicators to paper_trading_sessions

Revision ID: a1b2c3d4e5f6
Revises: c3d4e5f6a7b8
Create Date: 2026-09-27 16:00:00.000000

Adds a per-session ``use_technical_indicators`` flag making the technical-indicator
trend strategy opt-in. Chosen at build time and frozen for the session's lifetime.

Added with a ``false`` server default and backfilled to ``false`` for all existing
rows, so already-built sessions are treated as opted out and keep their prior
(pre-trend or unconditional-trend) behavior with no trend gate applied going forward.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_trading_sessions",
        sa.Column(
            "use_technical_indicators",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.execute(
        "UPDATE paper_trading_sessions SET use_technical_indicators = false "
        "WHERE use_technical_indicators IS NULL"
    )


def downgrade() -> None:
    op.drop_column("paper_trading_sessions", "use_technical_indicators")
