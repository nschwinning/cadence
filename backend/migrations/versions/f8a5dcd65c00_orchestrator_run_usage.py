"""orchestrator run usage

Revision ID: f8a5dcd65c00
Revises: dccd2472daa2
Create Date: 2026-11-10 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f8a5dcd65c00'
down_revision: str | Sequence[str] | None = 'dccd2472daa2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'bot_orchestrator_runs',
        sa.Column('usage', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bot_orchestrator_runs', 'usage')
