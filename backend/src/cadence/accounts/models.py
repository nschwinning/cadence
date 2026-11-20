"""ORM model for Cadence user accounts.

A ``users`` row exists for every person who has signed in (linked to their Keycloak
account by its subject id) plus one **legacy owner**: the placeholder that owns all data
created before ownership existed. Ownership columns on other tables reference
``users.id`` — never the Keycloak id directly, so a rebuilt or replaced identity provider
only needs accounts relinked, not every table rewritten.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from cadence.database import Base

#: Fixed id of the legacy owner, created by the ownership migration. Data created
#: without a signed-in user (background jobs, auth disabled, tests) belongs to it.
LEGACY_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class User(Base):
    """A Cadence account."""

    __tablename__ = "users"
    __table_args__ = (
        # At most one legacy owner.
        Index(
            "uq_users_single_legacy_owner",
            "is_legacy_owner",
            unique=True,
            postgresql_where=text("is_legacy_owner"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # The Keycloak subject id; NULL only for the legacy owner until its first sign-in.
    keycloak_sub: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_legacy_owner: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
