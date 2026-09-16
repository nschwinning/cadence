"""add alpaca_symbol to assets

Revision ID: c4e7a1f9b2d3
Revises: de5a2bf36170
Create Date: 2026-09-15 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e7a1f9b2d3'
down_revision: str | Sequence[str] | None = 'de5a2bf36170'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'assets', sa.Column('alpaca_symbol', sa.String(), nullable=True)
    )
    op.create_index(
        op.f('ix_assets_alpaca_symbol'), 'assets', ['alpaca_symbol'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_assets_alpaca_symbol'), table_name='assets')
    op.drop_column('assets', 'alpaca_symbol')
