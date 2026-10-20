"""add model paper-trading session column

Revision ID: f9b1c3e5a7d2
Revises: e8f3a1c5d2b4
Create Date: 2026-10-20 10:00:00.000000

Per-session, build-time-frozen AI model selection (a fixed-catalog member). Every
run for a session executes on the model frozen here at build time, so model choice
can be compared across sessions. Existing rows backfill to ``gpt-5-mini`` (the model
pre-existing sessions actually ran on), keeping per-run performance attribution
honest and leaving already-built sessions behaviorally unchanged.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f9b1c3e5a7d2'
down_revision: str | Sequence[str] | None = 'e8f3a1c5d2b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODEL_VALUES = ('gpt-5-mini', 'gpt-5.6-luna', 'gpt-6-luna')


def upgrade() -> None:
    """Upgrade schema."""
    # Non-nullable, added in three steps so existing rows backfill cleanly.
    op.add_column(
        'paper_trading_sessions',
        sa.Column(
            'model',
            sa.Enum(*_MODEL_VALUES, name='ai_model', native_enum=False),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE paper_trading_sessions SET model = 'gpt-5-mini' "
        "WHERE model IS NULL"
    )
    op.alter_column(
        'paper_trading_sessions',
        'model',
        existing_type=sa.Enum(*_MODEL_VALUES, name='ai_model', native_enum=False),
        nullable=False,
        server_default='gpt-5-mini',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('paper_trading_sessions', 'model')
