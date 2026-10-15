"""add watchlist membership, run target, and asset fundamentals

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-15 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: str | Sequence[str] | None = 'e1f2a3b4c5d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Which bucket an asset belongs to: the tradable ``universe`` (default) or
    # the emerging-candidates ``watchlist``. Non-native enum stored as VARCHAR
    # with a ``universe`` server default, so every pre-existing row is backfilled
    # as a universe member. Indexed because every asset-list and universe read
    # filters on it.
    op.add_column(
        'assets',
        sa.Column(
            'membership',
            sa.String(),
            nullable=False,
            server_default='universe',
        ),
    )
    op.create_index(
        op.f('ix_assets_membership'), 'assets', ['membership'], unique=False
    )

    # Which bucket a recommendation run populates (``universe`` default, or
    # ``watchlist``). Non-nullable with a ``universe`` server default so every
    # pre-existing run is a universe run.
    op.add_column(
        'recommendation_run',
        sa.Column(
            'target',
            sa.String(),
            nullable=False,
            server_default='universe',
        ),
    )

    # At most one SEC EDGAR fundamentals record per asset (1:1), enforced by the
    # unique constraint on ``asset_id``. Raw storage only; ``document`` is JSONB.
    op.create_table(
        'asset_fundamentals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('cik', sa.String(), nullable=True),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'fetched_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', name='uq_asset_fundamentals_asset'),
    )
    op.create_index(
        op.f('ix_asset_fundamentals_asset_id'),
        'asset_fundamentals',
        ['asset_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_asset_fundamentals_asset_id'), table_name='asset_fundamentals'
    )
    op.drop_table('asset_fundamentals')
    op.drop_column('recommendation_run', 'target')
    op.drop_index(op.f('ix_assets_membership'), table_name='assets')
    op.drop_column('assets', 'membership')
