"""link session runs to ai events

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-30 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: str | Sequence[str] | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Link each AI-driven run to the AI event that produced it.
    op.add_column(
        'session_runs',
        sa.Column('ai_portfolio_event_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_session_runs_ai_portfolio_event',
        'session_runs',
        'ai_portfolio_events',
        ['ai_portfolio_event_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'idx_session_runs_ai_event',
        'session_runs',
        ['ai_portfolio_event_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_session_runs_ai_event', table_name='session_runs')
    op.drop_constraint(
        'fk_session_runs_ai_portfolio_event', 'session_runs', type_='foreignkey'
    )
    op.drop_column('session_runs', 'ai_portfolio_event_id')
