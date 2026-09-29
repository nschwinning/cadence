"""add stop-loss opt-in to sessions and the stop_loss_quarantines table

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-29 10:00:00.000000

Adds the opt-in automatic hard stop-loss:

- ``paper_trading_sessions.stop_loss_enabled`` — per-session opt-in, chosen at
  build time and frozen. Non-nullable with a ``false`` server default and
  backfilled to ``false`` for existing rows, so already-built sessions behave as
  stop-loss off.
- ``paper_trading_sessions.stop_loss_pct`` — the frozen threshold as a fraction of
  weighted-average cost; nullable (meaningful only when enabled).
- ``stop_loss_quarantines`` — the per-session cooldown table keeping a just-stopped
  ticker out of rebalance candidates until ``excluded_until``.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: str | Sequence[str] | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_trading_sessions",
        sa.Column(
            "stop_loss_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.execute(
        "UPDATE paper_trading_sessions SET stop_loss_enabled = false "
        "WHERE stop_loss_enabled IS NULL"
    )
    op.add_column(
        "paper_trading_sessions",
        sa.Column("stop_loss_pct", sa.Float(), nullable=True),
    )

    op.create_table(
        "stop_loss_quarantines",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column(
            "excluded_until",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["paper_trading_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_stop_loss_quarantines_session_ticker",
        "stop_loss_quarantines",
        ["session_id", "ticker"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_stop_loss_quarantines_session_ticker",
        table_name="stop_loss_quarantines",
    )
    op.drop_table("stop_loss_quarantines")
    op.drop_column("paper_trading_sessions", "stop_loss_pct")
    op.drop_column("paper_trading_sessions", "stop_loss_enabled")
