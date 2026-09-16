"""link trades/closed positions to ai runs and store research transcript

Revision ID: e1f4c2a7b9d5
Revises: c4e7a1f9b2d3
Create Date: 2026-09-16 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e1f4c2a7b9d5'
down_revision: str | Sequence[str] | None = 'c4e7a1f9b2d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Per-run web-search transcript on the AI event.
    op.add_column(
        'ai_portfolio_events',
        sa.Column('research', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Link each trade to the AI run that produced it.
    op.add_column(
        'paper_trades',
        sa.Column('ai_portfolio_event_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_paper_trades_ai_portfolio_event',
        'paper_trades',
        'ai_portfolio_events',
        ['ai_portfolio_event_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'idx_paper_trades_ai_event',
        'paper_trades',
        ['ai_portfolio_event_id'],
        unique=False,
    )

    # Link each closed position to the AI run that closed it.
    op.add_column(
        'closed_positions',
        sa.Column('ai_portfolio_event_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_closed_positions_ai_portfolio_event',
        'closed_positions',
        'ai_portfolio_events',
        ['ai_portfolio_event_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'idx_closed_positions_ai_event',
        'closed_positions',
        ['ai_portfolio_event_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_closed_positions_ai_event', table_name='closed_positions')
    op.drop_constraint(
        'fk_closed_positions_ai_portfolio_event',
        'closed_positions',
        type_='foreignkey',
    )
    op.drop_column('closed_positions', 'ai_portfolio_event_id')

    op.drop_index('idx_paper_trades_ai_event', table_name='paper_trades')
    op.drop_constraint(
        'fk_paper_trades_ai_portfolio_event', 'paper_trades', type_='foreignkey'
    )
    op.drop_column('paper_trades', 'ai_portfolio_event_id')

    op.drop_column('ai_portfolio_events', 'research')
