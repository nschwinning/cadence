"""add asset_universe_evaluation

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-10-09 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f0a1b2c3d4e5'
down_revision: str | Sequence[str] | None = 'e9f0a1b2c3d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'asset_universe_evaluation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=False),
        sa.Column('strengths', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('concerns', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('suggestions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fingerprint', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('asset_universe_evaluation')
