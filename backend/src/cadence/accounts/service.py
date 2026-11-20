"""The signed-in user's Cadence account and what it may see and do.

:func:`current_account` resolves the account for a request:

* authentication disabled (local development, tests) → the **legacy owner**;
* a known Keycloak subject → that account (username and last sign-in refreshed);
* an unknown subject whose username equals ``CADENCE_LEGACY_OWNER`` while the legacy
  owner is still unlinked → the legacy owner, linked to that subject permanently (once);
* otherwise → a new, empty account.

Visibility: users see and act on only their own data; another user's object answers 404
(as if it did not exist). Admins may read everything (an ``all`` scope on lists, the
owner shown on objects) but are refused (403) when acting on someone else's object.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cadence.accounts.models import LEGACY_OWNER_ID, User
from cadence.auth import ADMIN, AuthUser, get_current_user
from cadence.config import settings
from cadence.database import get_db


@dataclass(frozen=True)
class Account:
    """The account a request acts as."""

    user_id: uuid.UUID
    username: str | None
    is_admin: bool


class Scope(StrEnum):
    """Which owners a list covers: the caller's own data, or (admins only) everyone's."""

    MINE = "mine"
    ALL = "all"


def resolve_user(db: Session, user: AuthUser, *, now: datetime | None = None) -> User:
    """Find, link or create the account for an authenticated Keycloak user."""
    now = now or datetime.now(UTC)
    account = db.execute(select(User).where(User.keycloak_sub == user.sub)).scalar_one_or_none()
    if account is None and settings.CADENCE_LEGACY_OWNER and (
        user.username == settings.CADENCE_LEGACY_OWNER
    ):
        legacy = db.execute(
            select(User)
            .where(User.id == LEGACY_OWNER_ID, User.keycloak_sub.is_(None))
            .with_for_update()
        ).scalar_one_or_none()
        if legacy is not None:
            legacy.keycloak_sub = user.sub
            account = legacy
    if account is None:
        account = User(keycloak_sub=user.sub)
        db.add(account)
    account.username = user.username
    account.last_login_at = now
    try:
        db.commit()
    except IntegrityError:
        # A concurrent first request created the account first: use that one.
        db.rollback()
        account = db.execute(select(User).where(User.keycloak_sub == user.sub)).scalar_one()
    return account


def current_account(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[AuthUser | None, Depends(get_current_user)],
) -> Account:
    """Route dependency: the account the request acts as (see the module docstring)."""
    if user is None:
        # Authentication disabled: everything acts as (and belongs to) the legacy owner.
        return Account(user_id=LEGACY_OWNER_ID, username=None, is_admin=True)
    cached = getattr(request.state, "account", None)
    if isinstance(cached, Account):
        return cached
    record = resolve_user(db, user)
    account = Account(user_id=record.id, username=record.username, is_admin=user.has(ADMIN))
    request.state.account = account
    return account


CurrentAccount = Annotated[Account, Depends(current_account)]


def list_scope(
    account: CurrentAccount,
    scope: Annotated[Scope, Query(description="mine (default) or all (admins only)")] = Scope.MINE,
) -> set[uuid.UUID] | None:
    """Owner filter for a list: the caller's id, or ``None`` (everyone) for an admin's ``all``."""
    if scope is Scope.ALL:
        if not account.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can list all users' data")
        return None
    return {account.user_id}


OwnerFilter = Annotated[set[uuid.UUID] | None, Depends(list_scope)]


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def ensure_can_read(account: Account, owner_id: uuid.UUID) -> None:
    """Own data, or any data for an admin; otherwise 404."""
    if owner_id != account.user_id and not account.is_admin:
        raise _not_found()


def ensure_can_act(account: Account, owner_id: uuid.UUID) -> None:
    """Own data only: 404 for other users, 403 for an admin acting on another's object."""
    if owner_id == account.user_id:
        return
    if account.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Admins can view but not change other users' data"
        )
    raise _not_found()


def owner_names(db: Session, owner_ids: set[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    """Usernames for owner ids (``None`` for the still-unlinked legacy owner)."""
    if not owner_ids:
        return {}
    rows = db.execute(select(User.id, User.username).where(User.id.in_(owner_ids))).all()
    return {row.id: row.username for row in rows}


def owner_name(db: Session, owner_id: uuid.UUID) -> str | None:
    """The username of one owner (``None`` for the still-unlinked legacy owner)."""
    return owner_names(db, {owner_id}).get(owner_id)
