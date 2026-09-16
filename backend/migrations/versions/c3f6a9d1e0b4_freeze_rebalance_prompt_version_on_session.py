"""freeze the rebalance prompt version on each paper-trading session

Revision ID: c3f6a9d1e0b4
Revises: a1d4e7c2b9f8
Create Date: 2026-09-16 13:00:00.000000

Each AI-managed session freezes the rebalance prompt version it was built with so
that adding a newer prompt version never changes an already-built session's
behavior. The column is non-nullable, so it is added in three steps: add nullable,
backfill every existing session to the highest existing prompt version (only
version 1 exists so far — seeded by ``a1d4e7c2b9f8``), then set NOT NULL.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f6a9d1e0b4'
down_revision: str | Sequence[str] | None = 'a1d4e7c2b9f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add nullable so the column can be created on a table that already has rows.
    op.add_column(
        "paper_trading_sessions",
        sa.Column("rebalance_prompt_version", sa.Integer(), nullable=True),
    )
    # 2. Backfill every existing session to the highest existing prompt version.
    op.execute(
        "UPDATE paper_trading_sessions "
        "SET rebalance_prompt_version = (SELECT MAX(version) FROM rebalance_prompt) "
        "WHERE rebalance_prompt_version IS NULL"
    )
    # 3. Enforce non-null going forward.
    op.alter_column(
        "paper_trading_sessions",
        "rebalance_prompt_version",
        existing_type=sa.Integer(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("paper_trading_sessions", "rebalance_prompt_version")
