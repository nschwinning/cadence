"""add price_history table

Revision ID: a9e4c7b2d8f1
Revises: f6a7b8c9d0e1
Create Date: 2026-10-01 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9e4c7b2d8f1'
down_revision: str | Sequence[str] | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Stored daily close prices per asset; one row per (asset, trading date).
    op.create_table(
        'price_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'asset_id', 'date', name='uq_price_history_asset_date'
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('price_history')
