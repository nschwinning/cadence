"""add broker_orders order journal

Revision ID: c3d5e7f9a1b2
Revises: 9b2e4c6d8f01
Create Date: 2026-11-11 12:00:00.000000

Write-ahead journal of every broker order Cadence sends: recorded (with a unique client
order id) before submission, updated with the broker's answer, and marked booked once
the owner's ledger reflects the fill. Unbooked rows are resolved by reconciliation.
Additive: a new table and its indexes only.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d5e7f9a1b2'
down_revision: str | Sequence[str] | None = '9b2e4c6d8f01'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the broker_orders journal."""
    op.create_table(
        'broker_orders',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('client_order_id', sa.Text(), nullable=False),
        sa.Column('owner_kind', sa.Text(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=True),
        sa.Column('ticker', sa.Text(), nullable=False),
        sa.Column('broker_symbol', sa.Text(), nullable=False),
        sa.Column('asset_class', sa.Text(), nullable=False),
        sa.Column('side', sa.Text(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=False),
        sa.Column(
            'context',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('broker_order_id', sa.Text(), nullable=True),
        sa.Column('broker_status', sa.Text(), nullable=True),
        sa.Column('filled_quantity', sa.Float(), nullable=True),
        sa.Column('filled_price', sa.Float(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('booked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_order_id'),
    )
    op.create_index('idx_broker_orders_owner', 'broker_orders', ['owner_kind', 'owner_id'])
    op.create_index(
        'idx_broker_orders_unresolved',
        'broker_orders',
        ['lease_until'],
        postgresql_where=sa.text("state IN ('intent', 'submitted') AND booked_at IS NULL"),
    )


def downgrade() -> None:
    """Drop the broker_orders journal."""
    op.drop_index(
        'idx_broker_orders_unresolved',
        table_name='broker_orders',
        postgresql_where=sa.text("state IN ('intent', 'submitted') AND booked_at IS NULL"),
    )
    op.drop_index('idx_broker_orders_owner', table_name='broker_orders')
    op.drop_table('broker_orders')
