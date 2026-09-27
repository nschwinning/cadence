"""add trend_context JSONB column to ai_portfolio_events

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-09-27 09:10:00.000000

Per-run trend-decision context on the AI event, mirroring the ``research`` column:
the candidates dropped by the trend gate (with reasons) and the indicator
annotations handed to the AI for the surviving candidates and holdings (with
reversal flags). Nullable; null for runs that did no gating.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | Sequence[str] | None = 'a7b8c9d0e1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ai_portfolio_events',
        sa.Column(
            'trend_context',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ai_portfolio_events', 'trend_context')
