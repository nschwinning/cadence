"""bot session preset provenance

Revision ID: 7dbcea076d4b
Revises: e5a1c9d2b7f3
Create Date: 2026-11-09 09:58:54.723565

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7dbcea076d4b'
down_revision: str | Sequence[str] | None = 'e5a1c9d2b7f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'bot_sessions',
        sa.Column('preset_key', sa.Text(), nullable=True),
    )
    op.add_column(
        'bot_sessions',
        sa.Column(
            'preset_customized',
            sa.Boolean(),
            server_default='false',
            nullable=False,
        ),
    )
    op.add_column(
        'bot_sessions',
        sa.Column('origin', sa.Text(), server_default='manual', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bot_sessions', 'origin')
    op.drop_column('bot_sessions', 'preset_customized')
    op.drop_column('bot_sessions', 'preset_key')
