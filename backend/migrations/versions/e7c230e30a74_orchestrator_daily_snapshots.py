"""orchestrator daily snapshots

Revision ID: e7c230e30a74
Revises: f8a5dcd65c00
Create Date: 2026-11-10 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7c230e30a74'
down_revision: str | Sequence[str] | None = 'f8a5dcd65c00'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bot_orchestrator_snapshots',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('orchestrator_id', sa.UUID(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('free_capital', sa.Float(), nullable=False),
        sa.Column('allocated_capital', sa.Float(), nullable=False),
        sa.Column('active_bots', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['orchestrator_id'], ['bot_orchestrators.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'orchestrator_id',
            'snapshot_date',
            name='uq_bot_orchestrator_snapshots_orchestrator_date',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('bot_orchestrator_snapshots')
