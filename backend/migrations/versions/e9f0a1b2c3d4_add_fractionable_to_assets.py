"""add fractionable to assets

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-10-08 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e9f0a1b2c3d4'
down_revision: str | Sequence[str] | None = 'd8e9f0a1b2c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'assets', sa.Column('fractionable', sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('assets', 'fractionable')
