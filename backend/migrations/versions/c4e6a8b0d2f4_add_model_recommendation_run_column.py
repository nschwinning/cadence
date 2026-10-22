"""add model recommendation-run column

Revision ID: c4e6a8b0d2f4
Revises: b2d4f6a8c0e2
Create Date: 2026-10-22 12:00:00.000000

Per-run AI model selection for the asset (universe) and watchlist recommenders.
Each run now records the model it executed on (a fixed-catalog AIModel value),
resolved at create time from the request or the configured default. Existing
rows backfill to ``gpt-5-mini`` (the model pre-existing runs actually ran on).
The server_default is dropped after the backfill so future inserts must supply
the value explicitly, matching how the service always resolves a concrete model.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e6a8b0d2f4'
down_revision: str | Sequence[str] | None = 'b2d4f6a8c0e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The model pre-existing runs actually executed on (== settings.RECOMMENDER_MODEL
# default == AIModel.GPT_5_MINI). Used only to backfill historical rows.
_BACKFILL_MODEL = 'gpt-5-mini'


def upgrade() -> None:
    """Upgrade schema."""
    # Non-nullable, added in three steps so existing rows backfill cleanly.
    op.add_column(
        'recommendation_run',
        sa.Column('model', sa.String(), nullable=True),
    )
    op.execute(
        f"UPDATE recommendation_run SET model = '{_BACKFILL_MODEL}' "
        "WHERE model IS NULL"
    )
    op.alter_column(
        'recommendation_run',
        'model',
        existing_type=sa.String(),
        nullable=False,
        server_default=_BACKFILL_MODEL,
    )
    # Drop the backfill default so future inserts must supply the resolved model.
    op.alter_column(
        'recommendation_run',
        'model',
        existing_type=sa.String(),
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('recommendation_run', 'model')
