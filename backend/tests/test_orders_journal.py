"""Tests for the write-ahead order journal and the order gateway."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.broker.base import OrderError
from cadence.broker.models import AssetClass, Order
from cadence.broker.stub import StubBroker
from cadence.orders import journal
from cadence.orders.gateway import OrderGateway, WouldShortError
from cadence.orders.models import BrokerOrder, JournalState, OrderOwnerKind


def _rows(db: Session) -> list[BrokerOrder]:
    db.expire_all()
    return list(db.execute(select(BrokerOrder).order_by(BrokerOrder.created_at)).scalars())


def _gateway(broker: StubBroker, kind: OrderOwnerKind = OrderOwnerKind.BOT) -> OrderGateway:
    return OrderGateway(broker, owner_kind=kind, owner_id=uuid.uuid4())


class _ExplodingBroker(StubBroker):
    def buy(self, *args: object, **kwargs: object) -> Order:  # type: ignore[override]
        raise OrderError("Alpaca API error: forbidden")


# --- journal ------------------------------------------------------------------
def test_intent_survives_the_callers_rollback(db_session: Session) -> None:
    client_id = journal.record_intent(
        owner_kind=OrderOwnerKind.BOT,
        owner_id=uuid.uuid4(),
        ticker="AAPL",
        broker_symbol="AAPL",
        asset_class="us_equity",
        side="buy",
        quantity=1,
        purpose="entry",
        context=None,
        lease=timedelta(minutes=2),
    )
    db_session.rollback()

    [row] = _rows(db_session)
    assert (row.client_order_id, row.state) == (client_id, JournalState.INTENT.value)
    assert client_id.startswith("cad-b-")


def test_mark_booked_twice_raises(db_session: Session) -> None:
    order = _gateway(StubBroker()).buy("AAPL", 1, purpose="entry")

    journal.mark_booked(db_session, order.client_order_id or "")
    with pytest.raises(journal.AlreadyBookedError):
        journal.mark_booked(db_session, order.client_order_id or "")


def test_client_order_ids_are_unique() -> None:
    ids = {journal.new_client_order_id(OrderOwnerKind.AI_SESSION) for _ in range(500)}
    assert len(ids) == 500


# --- gateway ------------------------------------------------------------------
def test_every_submit_is_journaled_with_its_client_id(db_session: Session) -> None:
    broker = StubBroker()

    order = _gateway(broker).buy("AAPL", 3, purpose="entry", context={"asset_id": 7})

    [row] = _rows(db_session)
    assert row.client_order_id == order.client_order_id
    assert broker.get_order_by_client_id(row.client_order_id) is not None
    assert (row.state, row.broker_status, row.filled_quantity) == ("submitted", "filled", 3)
    assert row.context == {"asset_id": 7}
    assert row.booked_at is None


def test_sell_more_than_held_is_refused(db_session: Session) -> None:
    broker = StubBroker()
    broker.buy("AAPL", 4)

    with pytest.raises(WouldShortError):
        _gateway(broker).sell("AAPL", 10, purpose="exit")

    [row] = _rows(db_session)
    assert row.state == JournalState.REFUSED.value
    assert broker.get_position("AAPL").quantity == 4  # type: ignore[union-attr]


def test_sell_of_an_unheld_symbol_is_refused(db_session: Session) -> None:
    with pytest.raises(WouldShortError):
        _gateway(StubBroker()).sell("XOM", 1, purpose="exit")


def test_sell_within_the_holding_proceeds(db_session: Session) -> None:
    broker = StubBroker()
    broker.buy("AAPL", 10)

    order = _gateway(broker).sell("AAPL", 4, purpose="exit")

    assert order.filled_quantity == 4
    assert broker.get_position("AAPL").quantity == 6  # type: ignore[union-attr]


def test_guard_matches_spellings(db_session: Session) -> None:
    broker = StubBroker()
    broker.buy("BRK.B", 2)

    order = _gateway(broker).sell("BRK-B", 2, purpose="exit", broker_symbol="BRK.B")

    assert order.filled_quantity == 2


def test_broker_error_leaves_the_row_submitted(db_session: Session) -> None:
    with pytest.raises(OrderError):
        _gateway(_ExplodingBroker()).buy("AAPL", 1, purpose="entry")

    [row] = _rows(db_session)
    assert row.state == JournalState.SUBMITTED.value
    assert "forbidden" in (row.error or "")
    # An explicit rejection hands the row to reconciliation at once (no lease wait).
    assert row.lease_until <= datetime.now(UTC)


def test_ambiguous_failure_keeps_the_lease(db_session: Session) -> None:
    class _TimeoutBroker(StubBroker):
        def buy(self, *args: object, **kwargs: object) -> Order:  # type: ignore[override]
            raise TimeoutError("read timed out")

    with pytest.raises(TimeoutError):
        _gateway(_TimeoutBroker()).buy("AAPL", 1, purpose="entry")

    [row] = _rows(db_session)
    assert row.lease_until > datetime.now(UTC)


def test_admin_orders_are_closed_at_submission(db_session: Session) -> None:
    _gateway(StubBroker(), OrderOwnerKind.ADMIN).buy(
        "BTC-USD", 0.5, purpose="admin_restore", asset_class=AssetClass.CRYPTO
    )

    [row] = _rows(db_session)
    assert row.state == JournalState.RESOLVED.value
    assert row.booked_at is not None
