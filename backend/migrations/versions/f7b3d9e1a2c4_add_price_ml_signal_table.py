"""add price_ml_signal table

Revision ID: f7b3d9e1a2c4
Revises: e2a4c6b8d0f1
Create Date: 2026-11-01 09:00:00.000000

One table backing the price-ML capability: ``price_ml_signal`` stores the latest
learned price-direction signal per asset (unique on ``asset_id``) — the predicted
direction and probability, the recent out-of-sample accuracy from the
walk-forward evaluation, the horizon, the as-of date, the model version, the
feature as-of date, and the bar count the features were drawn from. Each
precompute replaces the asset's row, so there is exactly one current signal per
asset. Empty until the first precompute runs; dropping the table is the rollback.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7b3d9e1a2c4'
down_revision: str | Sequence[str] | None = 'e2a4c6b8d0f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "price_ml_signal",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("recent_oos_accuracy", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("feature_as_of", sa.Date(), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_price_ml_signal_asset"),
    )
    op.create_index(
        op.f("ix_price_ml_signal_asset_id"),
        "price_ml_signal",
        ["asset_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_price_ml_signal_asset_id"), table_name="price_ml_signal")
    op.drop_table("price_ml_signal")
