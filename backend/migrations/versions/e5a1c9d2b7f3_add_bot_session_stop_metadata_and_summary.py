"""add bot session stop metadata and cached summary

Revision ID: e5a1c9d2b7f3
Revises: d4e8b2f6a1c7
Create Date: 2026-11-07 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5a1c9d2b7f3'
down_revision: str | Sequence[str] | None = 'd4e8b2f6a1c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'bot_sessions',
        sa.Column('stop_reason', sa.Text(), nullable=True),
    )
    op.add_column(
        'bot_sessions',
        sa.Column('stopped_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'bot_sessions',
        sa.Column('summary_narrative', sa.Text(), nullable=True),
    )
    op.add_column(
        'bot_sessions',
        sa.Column('summary_fingerprint', sa.Text(), nullable=True),
    )
    op.add_column(
        'bot_sessions',
        sa.Column('summary_model', sa.Text(), nullable=True),
    )
    op.add_column(
        'bot_sessions',
        sa.Column(
            'summary_generated_at', sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bot_sessions', 'summary_generated_at')
    op.drop_column('bot_sessions', 'summary_model')
    op.drop_column('bot_sessions', 'summary_fingerprint')
    op.drop_column('bot_sessions', 'summary_narrative')
    op.drop_column('bot_sessions', 'stopped_at')
    op.drop_column('bot_sessions', 'stop_reason')
