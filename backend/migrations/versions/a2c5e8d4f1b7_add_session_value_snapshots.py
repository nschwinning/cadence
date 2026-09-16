"""add session_value_snapshots

Revision ID: a2c5e8d4f1b7
Revises: f7b3d2a1c4e6
Create Date: 2026-09-16 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a2c5e8d4f1b7'
down_revision: str | Sequence[str] | None = 'f7b3d2a1c4e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'session_value_snapshots',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('cash_value', sa.Float(), nullable=False),
        sa.Column('positions_value', sa.Float(), nullable=False),
        sa.Column('daily_pnl', sa.Float(), nullable=False),
        sa.Column('daily_pnl_pct', sa.Float(), nullable=False),
        sa.Column('positions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['session_id'], ['paper_trading_sessions.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'session_id',
            'snapshot_date',
            name='uq_session_value_snapshots_session_date',
        ),
    )
    op.create_index(
        'idx_session_value_snapshots_session_date',
        'session_value_snapshots',
        ['session_id', 'snapshot_date'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'idx_session_value_snapshots_session_date',
        table_name='session_value_snapshots',
    )
    op.drop_table('session_value_snapshots')
