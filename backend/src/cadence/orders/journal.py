"""Journal writes for broker orders.

Rows are written through **independent, immediately committed sessions** (never the
caller's), so the record of an order survives whatever happens to the caller's unit of
work afterwards. The one exception is :func:`mark_booked`, which runs in the caller's
session on purpose: the booking mark must commit or roll back together with the ledger
writes it describes.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from cadence import database
from cadence.broker.models import Order
from cadence.broker.symbols import symbol_key
from cadence.orders.models import (
    UNRESOLVED_STATES,
    BrokerOrder,
    JournalState,
    OrderOwnerKind,
)

_KIND_TAG = {
    OrderOwnerKind.BOT: "b",
    OrderOwnerKind.AI_SESSION: "a",
    OrderOwnerKind.ADMIN: "x",
}


class AlreadyBookedError(Exception):
    """The order was already booked (or closed out) — the caller must not book it again."""


def _session_factory() -> Session:
    # Resolved per call so a rebound ``SessionLocal`` (tests) is honoured.
    return database.SessionLocal()


#: Overridable in tests; production writes through the app's ``SessionLocal``.
session_factory: Callable[[], Session] = _session_factory


@contextmanager
def _independent() -> Iterator[Session]:
    db = session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _now() -> datetime:
    return datetime.now(UTC)


def new_client_order_id(owner_kind: OrderOwnerKind) -> str:
    """A client order id unique across every order Cadence has ever sent."""
    return f"cad-{_KIND_TAG[owner_kind]}-{uuid.uuid4().hex}"


def record_intent(
    *,
    owner_kind: OrderOwnerKind,
    owner_id: uuid.UUID | None,
    ticker: str,
    broker_symbol: str,
    asset_class: str,
    side: str,
    quantity: float,
    purpose: str,
    context: dict[str, Any] | None,
    lease: timedelta,
    state: JournalState = JournalState.INTENT,
    error: str | None = None,
) -> str:
    """Durably record an intended order before it is sent; return its client order id."""
    client_order_id = new_client_order_id(owner_kind)
    with _independent() as db:
        db.add(
            BrokerOrder(
                client_order_id=client_order_id,
                owner_kind=owner_kind.value,
                owner_id=owner_id,
                ticker=ticker,
                broker_symbol=broker_symbol,
                asset_class=asset_class,
                side=side,
                quantity=quantity,
                purpose=purpose,
                context=context or {},
                state=state.value,
                error=error,
                lease_until=_now() + lease,
            )
        )
    return client_order_id


def record_submitted(
    client_order_id: str,
    *,
    order: Order | None,
    error: str | None = None,
    resolved: bool = False,
    expire_lease: bool = False,
) -> None:
    """Record the broker's answer (or the submission error) for an intended order.

    The row stays ``submitted`` even on an error: the broker may have received the order
    before the failure, so only reconciliation can tell. ``resolved`` closes the row as
    booked right away (administrator orders, which have no ledger to book into).
    ``expire_lease`` hands the row to reconciliation immediately — used when the broker
    explicitly rejected the order, so the next pass confirms there is nothing to book
    instead of keeping the owner's symbol blocked for the whole lease.
    """
    values: dict[str, Any] = {"state": JournalState.SUBMITTED.value, "error": error}
    if order is not None:
        values.update(
            broker_order_id=order.order_id,
            broker_status=order.status.value,
            filled_quantity=order.filled_quantity,
            filled_price=order.filled_price,
        )
    if resolved and error is None:
        values.update(state=JournalState.RESOLVED.value, booked_at=_now())
    if expire_lease:
        values["lease_until"] = _now()
    with _independent() as db:
        db.execute(
            update(BrokerOrder)
            .where(BrokerOrder.client_order_id == client_order_id)
            .values(**values)
        )


def mark_booked(db: Session, client_order_id: str) -> None:
    """Mark an order booked in the caller's unit of work (alongside its ledger writes).

    Raises :class:`AlreadyBookedError` when the row was already booked or closed out —
    e.g. reconciliation got there first — so the caller does not book it twice.
    """
    result = db.execute(
        update(BrokerOrder)
        .where(BrokerOrder.client_order_id == client_order_id)
        .where(BrokerOrder.booked_at.is_(None))
        .where(BrokerOrder.state.in_(UNRESOLVED_STATES))
        .values(booked_at=_now(), state=JournalState.RESOLVED.value)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise AlreadyBookedError(client_order_id)


def has_unresolved(
    db: Session, *, owner_kind: OrderOwnerKind, owner_id: uuid.UUID, ticker: str
) -> bool:
    """Whether the owner still has an unbooked, unresolved order for ``ticker``."""
    key = symbol_key(ticker)
    rows = db.execute(
        select(BrokerOrder.ticker)
        .where(BrokerOrder.owner_kind == owner_kind.value)
        .where(BrokerOrder.owner_id == owner_id)
        .where(BrokerOrder.booked_at.is_(None))
        .where(BrokerOrder.state.in_(UNRESOLVED_STATES))
    ).scalars()
    return any(symbol_key(t) == key for t in rows)


def list_unresolved(db: Session) -> list[BrokerOrder]:
    """Every unbooked, unresolved order, oldest first."""
    return list(
        db.execute(
            select(BrokerOrder)
            .where(BrokerOrder.booked_at.is_(None))
            .where(BrokerOrder.state.in_(UNRESOLVED_STATES))
            .order_by(BrokerOrder.created_at)
        ).scalars()
    )
