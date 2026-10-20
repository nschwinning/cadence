"""add model column to ai_portfolio_events

Revision ID: a1c3e5f7b9d2
Revises: f9b1c3e5a7d2
Create Date: 2026-10-20 10:05:00.000000

Record which AI model produced each run, for per-run performance attribution. The
column is nullable: historical events and runs that failed before reaching the
agent carry null.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c3e5f7b9d2'
down_revision: str | Sequence[str] | None = 'f9b1c3e5a7d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ai_portfolio_events',
        sa.Column('model', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ai_portfolio_events', 'model')
