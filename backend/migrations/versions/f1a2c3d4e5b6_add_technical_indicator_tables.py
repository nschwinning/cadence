"""add technical_indicator and technical_indicator_run tables

Revision ID: f1a2c3d4e5b6
Revises: e5c9a3f7d2b8
Create Date: 2026-09-27 09:00:00.000000

Two tables backing the technical-indicator capability:

* ``technical_indicator`` — the latest indicator snapshot per asset (unique on
  ``asset_id``): the close+volume indicator set (all nullable — NULL when history
  is insufficient), the deterministic gate verdict + sub-verdicts, and the
  boolean reversal flags.
* ``technical_indicator_run`` — a run-audit row for each nightly precompute.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2c3d4e5b6'
down_revision: str | Sequence[str] | None = 'e5c9a3f7d2b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FLOAT_COLUMNS = (
    "close",
    "sma_50",
    "sma_200",
    "close_sma200",
    "sma50_sma200",
    "sma200_slope",
    "ema_20",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "rsi_14",
    "roc_120",
    "obv",
    "obv_change_20d",
    "vol_ratio_50",
    "dist_high_52w",
    "drawdown_from_max",
    "hvol_20",
    "bb_pctb",
    "bb_width",
)

_BOOL_COLUMNS = (
    "gate_pass",
    "regime_pass",
    "momentum_pass",
    "obv_rising",
    "rev_macd_hist_rollover",
    "rev_rsi_rollover",
    "rev_return_decel",
    "rev_obv_price_divergence",
    "rev_sma200_slope_flattening",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "technical_indicator",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        *[sa.Column(name, sa.Float(), nullable=True) for name in _FLOAT_COLUMNS],
        *[sa.Column(name, sa.Boolean(), nullable=False) for name in _BOOL_COLUMNS],
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_technical_indicator_asset"),
    )
    op.create_index(
        op.f("ix_technical_indicator_asset_id"),
        "technical_indicator",
        ["asset_id"],
        unique=False,
    )

    op.create_table(
        "technical_indicator_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                name="runphase",
                native_enum=False,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "assets_processed", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("assets_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("technical_indicator_run")
    op.drop_index(
        op.f("ix_technical_indicator_asset_id"), table_name="technical_indicator"
    )
    op.drop_table("technical_indicator")
