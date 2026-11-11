"""Resolve journaled orders their owner never booked.

A row is a candidate once it is unbooked, still ``intent``/``submitted``, and its owner's
lease has expired (so an owner still working on it is never raced). Each candidate is
looked up at the broker by its client order id and then:

- **not found** → ``not_submitted``: the broker never received it, nothing to book;
- **terminal with a fill** → the filled quantity is booked into the owning bot or AI
  portfolio exactly once (the journal's booked mark commits with the ledger writes);
- **terminal without a fill** (rejected / cancelled / expired) → resolved, nothing booked;
- **still working** → left for a later pass.

Every row is processed and committed on its own, so one failure never blocks the rest.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from cadence.broker.base import Broker, BrokerError
from cadence.broker.models import AssetClass, Order, OrderSide
from cadence.orders import journal
from cadence.orders.models import (
    UNRESOLVED_STATES,
    BrokerOrder,
    JournalState,
    OrderOwnerKind,
)

_logger = logging.getLogger(__name__)

#: Signal type stamped on AI-portfolio trades booked by reconciliation.
RECONCILED_SIGNAL_SUFFIX = "_reconciled"


@dataclass(frozen=True)
class ReconcileResult:
    """How many journal rows a pass booked, closed out without booking, or left open."""

    booked: int = 0
    closed: int = 0
    remaining: int = 0


def reconcile_orders(
    db: Session,
    broker: Broker,
    *,
    owner_kind: OrderOwnerKind | None = None,
    owner_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> ReconcileResult:
    """Resolve every unbooked journal row whose lease has expired (optionally one owner's)."""
    now = now or datetime.now(UTC)
    stmt = (
        select(BrokerOrder.id)
        .where(BrokerOrder.booked_at.is_(None))
        .where(BrokerOrder.state.in_(UNRESOLVED_STATES))
        .where(BrokerOrder.lease_until < now)
        .order_by(BrokerOrder.created_at)
    )
    if owner_kind is not None:
        stmt = stmt.where(BrokerOrder.owner_kind == owner_kind.value)
    if owner_id is not None:
        stmt = stmt.where(BrokerOrder.owner_id == owner_id)
    ids = list(db.execute(stmt).scalars())

    booked = closed = remaining = 0
    for row_id in ids:
        try:
            outcome = _resolve_one(db, broker, row_id)
            db.commit()
        except Exception:
            db.rollback()
            _logger.warning("reconcile: journal row %s failed", row_id, exc_info=True)
            outcome = "remaining"
        if outcome == "booked":
            booked += 1
        elif outcome == "closed":
            closed += 1
        elif outcome == "remaining":
            remaining += 1
    return ReconcileResult(booked=booked, closed=closed, remaining=remaining)


def _resolve_one(db: Session, broker: Broker, row_id: uuid.UUID) -> str:
    """Resolve one row in the caller's unit of work; return its outcome."""
    row = db.execute(
        select(BrokerOrder)
        .where(BrokerOrder.id == row_id)
        .where(BrokerOrder.booked_at.is_(None))
        .where(BrokerOrder.state.in_(UNRESOLVED_STATES))
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if row is None:  # resolved meanwhile, or another pass holds it
        return "skipped"

    try:
        order = broker.get_order_by_client_id(row.client_order_id)
    except BrokerError:
        _logger.warning("reconcile: could not look up %s", row.client_order_id, exc_info=True)
        return "remaining"

    if order is None:
        _set_state(db, row, JournalState.NOT_SUBMITTED)
        _logger.info("reconcile: %s never reached the broker", row.client_order_id)
        return "closed"

    row.broker_order_id = order.order_id
    row.broker_status = order.status.value
    row.filled_quantity = order.filled_quantity
    row.filled_price = order.filled_price
    if not order.is_complete:
        row.state = JournalState.SUBMITTED.value
        return "remaining"

    if order.filled_quantity <= 0 or order.filled_price is None:
        _set_state(db, row, JournalState.RESOLVED)
        return "closed"

    _book(db, row, order)
    _logger.info(
        "reconcile: booked %s %s %s for %s %s",
        row.side,
        order.filled_quantity,
        row.ticker,
        row.owner_kind,
        row.owner_id,
    )
    return "booked"


def _set_state(db: Session, row: BrokerOrder, state: JournalState) -> None:
    db.execute(
        update(BrokerOrder)
        .where(BrokerOrder.id == row.id)
        .values(state=state.value)
        .execution_options(synchronize_session=False)
    )
    row.state = state.value


def _book(db: Session, row: BrokerOrder, order: Order) -> None:
    """Book a terminal fill into the row's owner and mark the row booked."""
    kind = OrderOwnerKind(row.owner_kind)
    if kind is OrderOwnerKind.ADMIN or row.owner_id is None:
        journal.mark_booked(db, row.client_order_id)
        return
    if kind is OrderOwnerKind.BOT:
        _book_bot(db, row, order)
    else:
        _book_ai_session(db, row, order)


def _book_bot(db: Session, row: BrokerOrder, order: Order) -> None:
    from cadence.strategy_bots.engine import book_entry_fill, book_exit_fill
    from cadence.strategy_bots.models import BotSession

    bot = db.get(BotSession, row.owner_id)
    if bot is None:
        _logger.warning("reconcile: bot %s no longer exists; not booking", row.owner_id)
        journal.mark_booked(db, row.client_order_id)
        return
    journal.mark_booked(db, row.client_order_id)
    quantity = order.filled_quantity
    price = order.filled_price or 0.0
    reason = f"{row.purpose}{RECONCILED_SIGNAL_SUFFIX}"
    if row.side == OrderSide.BUY.value:
        book_entry_fill(
            db,
            bot,
            asset_id=int(row.context.get("asset_id", 0)),
            ticker=row.ticker,
            symbol=row.broker_symbol,
            quantity=quantity,
            price=price,
            order=order,
            now=order.filled_at or datetime.now(UTC),
            reason=reason,
        )
    else:
        book_exit_fill(
            db,
            bot,
            ticker=row.ticker,
            symbol=row.broker_symbol,
            quantity=quantity,
            price=price,
            order=order,
            reason=reason,
        )


def _book_ai_session(db: Session, row: BrokerOrder, order: Order) -> None:
    from cadence.paper_trading import service as paper_service
    from cadence.paper_trading.models import PaperTradingSession

    if db.get(PaperTradingSession, row.owner_id) is None:
        _logger.warning("reconcile: session %s no longer exists; not booking", row.owner_id)
        journal.mark_booked(db, row.client_order_id)
        return
    event_id = row.context.get("event_id")
    paper_service.book_fill(
        db,
        session_id=row.owner_id,  # type: ignore[arg-type]
        ticker=row.ticker,
        side=OrderSide(row.side),
        quantity=order.filled_quantity,
        price=order.filled_price or 0.0,
        filled_price=order.filled_price,
        signal_type=f"{row.purpose}{RECONCILED_SIGNAL_SUFFIX}",
        asset_class=AssetClass(row.asset_class),
        order_id=order.order_id,
        order_status=order.status,
        ai_portfolio_event_id=uuid.UUID(event_id) if event_id else None,
        client_order_id=row.client_order_id,
        now=order.filled_at,
    )
