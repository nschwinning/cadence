"""add user accounts and data ownership

Revision ID: e1f3a5c7b9d2
Revises: d4f6a8b0c2e3
Create Date: 2026-11-19 12:00:00.000000

Creates ``users`` with the **legacy owner** (fixed id, not yet linked to a Keycloak
account; the first sign-in of ``CADENCE_LEGACY_OWNER`` links it) and adds owner columns:
``portfolios``, ``ai_portfolio_events``, ``bot_orchestrators`` and ``bot_sessions`` get
``owner_user_id``; ``broker_orders`` gets ``account_user_id``. Every existing row is
assigned to the legacy owner, the result is verified (every row owned; every
orchestrator-deployed bot owned by its orchestrator's owner) and only then are the
columns made NOT NULL. A failed check aborts the migration without changes.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1f3a5c7b9d2'
down_revision: str | Sequence[str] | None = 'd4f6a8b0c2e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_OWNER_ID = '00000000-0000-0000-0000-000000000001'

#: (table, owner column) pairs that get an owner.
_OWNED = (
    ('portfolios', 'owner_user_id'),
    ('ai_portfolio_events', 'owner_user_id'),
    ('bot_orchestrators', 'owner_user_id'),
    ('bot_sessions', 'owner_user_id'),
    ('broker_orders', 'account_user_id'),
)


def upgrade() -> None:
    """Create users + legacy owner, add owner columns, backfill, verify, enforce."""
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('keycloak_sub', sa.Text(), nullable=True),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('is_legacy_owner', sa.Boolean(), server_default='false', nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('keycloak_sub'),
    )
    op.create_index(
        'uq_users_single_legacy_owner',
        'users',
        ['is_legacy_owner'],
        unique=True,
        postgresql_where=sa.text('is_legacy_owner'),
    )
    op.execute(
        sa.text(
            "INSERT INTO users (id, is_legacy_owner) VALUES (CAST(:id AS uuid), true)"
        ).bindparams(id=LEGACY_OWNER_ID)
    )

    for table, column in _OWNED:
        op.add_column(table, sa.Column(column, sa.UUID(), nullable=True))
        op.execute(
            sa.text(f"UPDATE {table} SET {column} = CAST(:id AS uuid)").bindparams(
                id=LEGACY_OWNER_ID
            )
        )

    bind = op.get_bind()
    for table, column in _OWNED:
        unowned = bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {column} IS NULL")).scalar()
        if unowned:
            raise RuntimeError(f"ownership migration: {unowned} rows of {table} have no owner")
    mismatched = bind.execute(
        sa.text(
            "SELECT count(*) FROM bot_sessions b JOIN bot_orchestrators o "
            "ON o.id = b.orchestrator_id WHERE b.owner_user_id <> o.owner_user_id"
        )
    ).scalar()
    if mismatched:
        raise RuntimeError(
            f"ownership migration: {mismatched} orchestrator bots not owned by their orchestrator's owner"
        )

    for table, column in _OWNED:
        op.alter_column(table, column, nullable=False)
        op.create_index(f'ix_{table}_{column}', table, [column])
        op.create_foreign_key(
            f'fk_{table}_{column}_users', table, 'users', [column], ['id'], ondelete='RESTRICT'
        )


def downgrade() -> None:
    """Drop the owner columns and the users table (the data itself is untouched)."""
    for table, column in reversed(_OWNED):
        op.drop_constraint(f'fk_{table}_{column}_users', table, type_='foreignkey')
        op.drop_index(f'ix_{table}_{column}', table_name=table)
        op.drop_column(table, column)
    op.drop_index('uq_users_single_legacy_owner', table_name='users')
    op.drop_table('users')
