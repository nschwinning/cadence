"""initial schema-light baseline

Revision ID: 2799eb86ac4c
Revises:
Create Date: 2026-08-28 18:49:42.374767

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '2799eb86ac4c'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
