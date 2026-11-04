"""add bot_value_points (intraday value capture)

Add the ``bot_value_points`` table: one timestamped portfolio-value point per bot
session per tick, feeding the chart's intraday (``5min``) and ``hourly`` resolutions.
Pruned to a retention window by the daily snapshot job, so the table stays bounded.
No change to existing tables.

Revision ID: d4e8b2f6a1c7
Revises: b7d1f3a5c9e2
Create Date: 2026-11-03 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e8b2f6a1c7'
down_revision: str | Sequence[str] | None = 'b7d1f3a5c9e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bot_value_points',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('bot_session_id', sa.UUID(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('realised_pnl', sa.Float(), nullable=False),
        sa.Column('unrealised_pnl', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ['bot_session_id'], ['bot_sessions.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_bot_value_points_session_time',
        'bot_value_points',
        ['bot_session_id', 'captured_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'idx_bot_value_points_session_time',
        table_name='bot_value_points',
    )
    op.drop_table('bot_value_points')
