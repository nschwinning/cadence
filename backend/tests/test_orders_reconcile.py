"""Tests for reconciling journaled orders their owner never booked."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_admin_account import _ai_session

from cadence.assets.models import Asset
from cadence.broker.base import BrokerError
from cadence.broker.models import Order, OrderStatus
from cadence.broker.stub import StubBroker
from cadence.orders import journal
from cadence.orders.gateway import OrderGateway
from cadence.orders.models import BrokerOrder, JournalState, OrderOwnerKind
from cadence.orders.reconcile import reconcile_orders
from cadence.paper_trading.models import PaperTrade, SessionPosition
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.models import BotSession, BotTrade

#: Past every owner's lease.
_LATER = datetime.now(UTC) + timedelta(hours=1)


def _bot(db: Session, ticker: str = "AAPL") -> BotSession:
    db.add(
        Asset(
            ticker=ticker,
            name=ticker,
            sector="technology",
            category="stock",
            currency="USD",
            is_eligible=True,
            criteria_results=[],
        )
    )
    db.flush()
    return bot_service.create_bot_session(
        db,
        preset_key="donchian_turtle_algo25",
        tickers=[ticker],
        initial_capital=10_000.0,
        benchmark="SP500",
    )


def _row(db: Session, client_order_id: str) -> BrokerOrder:
    db.expire_all()
    return db.execute(
        select(BrokerOrder).where(BrokerOrder.client_order_id == client_order_id)
    ).scalar_one()


class _WorkingBroker(StubBroker):
    """Orders are accepted but stay working until the test fills or cancels them."""

    def submit_order(self, order: Order) -> Order:
        order.order_id = self._next_order_id()
        order.status = OrderStatus.SUBMITTED
        self._orders[order.order_id] = order
        return order

    def settle(
        self, client_order_id: str, *, status: OrderStatus, qty: float, price: float | None
    ) -> None:
        order = self.get_order_by_client_id(client_order_id)
        assert order is not None
        order.status = status
        order.filled_quantity = qty
        order.filled_price = price
        order.filled_at = datetime.now(UTC)


# --- bot fills -----------------------------------------------------------------
def test_fill_lost_to_a_rollback_is_booked_once(db_session: Session) -> None:
    bot = _bot(db_session)
    asset_id = bot.symbols[0].asset_id
    broker = StubBroker()
    gateway = OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id)
    order = gateway.buy("AAPL", 5, purpose="entry", context={"asset_id": asset_id})
    # The tick that sent it failed before booking: nothing recorded on the bot.
    assert bot.positions == []

    result = reconcile_orders(db_session, broker, now=_LATER)

    assert (result.booked, result.closed, result.remaining) == (1, 0, 0)
    db_session.refresh(bot)
    [position] = bot.positions
    assert (position.ticker, position.quantity, position.asset_id) == ("AAPL", 5, asset_id)
    assert bot.cash == pytest.approx(10_000.0 - 5 * (order.filled_price or 0))
    [trade] = db_session.execute(select(BotTrade)).scalars()
    assert trade.reason == "entry_reconciled"
    assert _row(db_session, order.client_order_id or "").booked_at is not None

    again = reconcile_orders(db_session, broker, now=_LATER)
    assert again.booked == 0
    assert len(list(db_session.execute(select(BotTrade)).scalars())) == 1


def test_unbooked_sell_closes_the_position(db_session: Session) -> None:
    bot = _bot(db_session)
    broker = StubBroker()
    gateway = OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id)
    entry = gateway.buy("AAPL", 5, purpose="entry", context={"asset_id": bot.symbols[0].asset_id})
    reconcile_orders(db_session, broker, now=_LATER)
    db_session.refresh(bot)
    assert entry.filled_price is not None

    gateway.sell("AAPL", 5, purpose="session_stopped")
    reconcile_orders(db_session, broker, now=_LATER)

    db_session.refresh(bot)
    assert bot.positions == []
    assert bot.cash == pytest.approx(10_000.0)
    assert bot.realised_pnl == pytest.approx(0.0)


def test_late_fill_after_poll_timeout_is_booked(db_session: Session) -> None:
    bot = _bot(db_session)
    broker = _WorkingBroker()
    gateway = OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id)
    order = gateway.buy("AAPL", 3, purpose="entry", context={"asset_id": bot.symbols[0].asset_id})
    client_id = order.client_order_id or ""

    still_working = reconcile_orders(db_session, broker, now=_LATER)
    assert (still_working.booked, still_working.remaining) == (0, 1)

    broker.settle(client_id, status=OrderStatus.FILLED, qty=3, price=120.0)
    filled = reconcile_orders(db_session, broker, now=_LATER)

    assert filled.booked == 1
    db_session.refresh(bot)
    assert [(p.quantity, p.avg_price) for p in bot.positions] == [(3, 120.0)]


def test_partial_fill_then_cancel_books_the_filled_part(db_session: Session) -> None:
    bot = _bot(db_session)
    broker = _WorkingBroker()
    gateway = OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id)
    order = gateway.buy("AAPL", 5, purpose="entry", context={"asset_id": bot.symbols[0].asset_id})
    broker.settle(order.client_order_id or "", status=OrderStatus.CANCELLED, qty=2, price=100.0)

    reconcile_orders(db_session, broker, now=_LATER)

    db_session.refresh(bot)
    assert [p.quantity for p in bot.positions] == [2]


def test_rejected_without_fill_is_closed_without_booking(db_session: Session) -> None:
    bot = _bot(db_session)
    broker = _WorkingBroker()
    gateway = OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id)
    order = gateway.buy("AAPL", 5, purpose="entry", context={"asset_id": bot.symbols[0].asset_id})
    broker.settle(order.client_order_id or "", status=OrderStatus.REJECTED, qty=0, price=None)

    result = reconcile_orders(db_session, broker, now=_LATER)

    assert (result.booked, result.closed) == (0, 1)
    db_session.refresh(bot)
    assert bot.positions == []
    assert _row(db_session, order.client_order_id or "").state == JournalState.RESOLVED.value


def test_order_that_never_reached_the_broker_is_closed(db_session: Session) -> None:
    client_id = journal.record_intent(
        owner_kind=OrderOwnerKind.BOT,
        owner_id=uuid.uuid4(),
        ticker="AAPL",
        broker_symbol="AAPL",
        asset_class="equity",
        side="buy",
        quantity=1,
        purpose="entry",
        context=None,
        lease=timedelta(minutes=2),
    )

    result = reconcile_orders(db_session, StubBroker(), now=_LATER)

    assert result.closed == 1
    assert _row(db_session, client_id).state == JournalState.NOT_SUBMITTED.value


def test_in_lease_order_is_left_alone(db_session: Session) -> None:
    bot = _bot(db_session)
    broker = StubBroker()
    OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id).buy(
        "AAPL", 1, purpose="entry", context={"asset_id": bot.symbols[0].asset_id}
    )

    result = reconcile_orders(db_session, broker)  # now: still inside the 2-minute lease

    assert (result.booked, result.closed, result.remaining) == (0, 0, 0)
    db_session.refresh(bot)
    assert bot.positions == []


def test_one_failing_record_does_not_stop_the_others(db_session: Session) -> None:
    bot = _bot(db_session)

    class _FlakyLookup(StubBroker):
        def __init__(self) -> None:
            super().__init__()
            self.broken: str | None = None

        def get_order_by_client_id(self, client_order_id: str) -> Order | None:
            if client_order_id == self.broken:
                raise BrokerError("lookup failed")
            return super().get_order_by_client_id(client_order_id)

    broker = _FlakyLookup()
    gateway = OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id)
    context: dict[str, Any] = {"asset_id": bot.symbols[0].asset_id}
    first = gateway.buy("AAPL", 1, purpose="entry", context=context)
    gateway.buy("AAPL", 2, purpose="entry", context=context)
    broker.broken = first.client_order_id

    result = reconcile_orders(db_session, broker, now=_LATER)

    assert (result.booked, result.remaining) == (1, 1)


def test_owner_filter_limits_the_pass(db_session: Session) -> None:
    bot = _bot(db_session)
    broker = StubBroker()
    OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id).buy(
        "AAPL", 1, purpose="entry", context={"asset_id": bot.symbols[0].asset_id}
    )

    result = reconcile_orders(db_session, broker, owner_kind=OrderOwnerKind.AI_SESSION, now=_LATER)

    assert result.booked == 0


def test_caller_booking_after_reconciliation_is_refused(db_session: Session) -> None:
    bot = _bot(db_session)
    broker = StubBroker()
    order = OrderGateway(broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id).buy(
        "AAPL", 1, purpose="entry", context={"asset_id": bot.symbols[0].asset_id}
    )
    reconcile_orders(db_session, broker, now=_LATER)

    with pytest.raises(journal.AlreadyBookedError):
        journal.mark_booked(db_session, order.client_order_id or "")


# --- AI-portfolio fills -------------------------------------------------------
def test_ai_session_fill_lost_to_a_failed_run_is_booked_once(db_session: Session) -> None:
    row = _ai_session(db_session, capital=10_000.0)
    broker = StubBroker()
    order = OrderGateway(broker, owner_kind=OrderOwnerKind.AI_SESSION, owner_id=row.id).buy(
        "MSFT", 4, purpose="ai_rebalance_buy"
    )

    result = reconcile_orders(db_session, broker, now=_LATER)

    assert result.booked == 1
    [position] = db_session.execute(select(SessionPosition)).scalars()
    assert (position.ticker, position.quantity) == ("MSFT", 4)
    assert position.avg_cost == order.filled_price
    [trade] = db_session.execute(select(PaperTrade)).scalars()
    assert trade.signal_type == "ai_rebalance_buy_reconciled"
    assert reconcile_orders(db_session, broker, now=_LATER).booked == 0


# --- admin --------------------------------------------------------------------
def test_unfinished_admin_order_is_closed_without_ledger_changes(db_session: Session) -> None:
    broker = StubBroker()

    class _Exploding(StubBroker):
        def buy(self, *args: object, **kwargs: Any) -> Order:  # type: ignore[override]
            order = broker.buy(*args, **kwargs)  # type: ignore[arg-type]
            raise BrokerError(f"timeout after submit {order.order_id}")

    with pytest.raises(BrokerError):
        OrderGateway(_Exploding(), owner_kind=OrderOwnerKind.ADMIN).buy(
            "XOM", 2, purpose="admin_restore"
        )

    result = reconcile_orders(db_session, broker, now=_LATER)

    assert result.booked == 1
    assert list(db_session.execute(select(PaperTrade)).scalars()) == []
    assert list(db_session.execute(select(BotTrade)).scalars()) == []
