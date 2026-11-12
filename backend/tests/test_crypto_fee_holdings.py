"""Crypto holdings vs the broker's coin-denominated fee, the $10 crypto minimum, write-offs."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_admin_account import _ai_session, _broker, _ledger, _row

from cadence.admin import service as admin_service
from cadence.ai_portfolio.executor import MIN_CRYPTO_NOTIONAL_USD, AIPortfolioExecutor
from cadence.broker.base import OrderError
from cadence.broker.models import AssetClass, Order, OrderStatus, Position
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.orders import journal
from cadence.orders.gateway import OrderGateway
from cadence.orders.models import BrokerOrder, JournalState, OrderOwnerKind
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.models import PaperTrade, SessionPosition


def _book(db: Session, session_id: object, side: str, qty: float, cls: AssetClass) -> None:
    from cadence.broker.models import OrderSide

    paper_service.book_fill(
        db,
        session_id=session_id,  # type: ignore[arg-type]
        ticker="ADA-USD" if cls is AssetClass.CRYPTO else "AAPL",
        side=OrderSide(side),
        quantity=qty,
        price=0.5,
        filled_price=0.5,
        signal_type="ai_rebalance_" + side,
        asset_class=cls,
        order_id=None,
        order_status=OrderStatus.FILLED,
    )


class _CryptoAwareStub(StubBroker):
    """Stub that, like Alpaca, reports ``-USD`` pairs as crypto positions."""

    def get_positions(self) -> list[Position]:
        positions = super().get_positions()
        for p in positions:
            p.asset_class = AssetClass.CRYPTO if p.symbol.endswith("-USD") else AssetClass.EQUITY
        return positions


def _crypto_broker(*holdings: tuple[str, float]) -> _CryptoAwareStub:
    broker = _CryptoAwareStub(initial_cash=10_000_000.0)
    for symbol, qty in holdings:
        broker.buy(symbol, qty)
    return broker


# --- booking ---------------------------------------------------------------------------
def test_crypto_buy_is_booked_net_of_the_fee(db_session: Session) -> None:
    assert settings.CRYPTO_FEE_PCT == pytest.approx(0.0025)
    row = _ai_session(db_session, capital=10_000.0)

    _book(db_session, row.id, "buy", 1_000, AssetClass.CRYPTO)

    [position] = db_session.execute(select(SessionPosition)).scalars()
    assert (position.quantity, position.avg_cost) == (pytest.approx(997.5), 0.5)
    [trade] = db_session.execute(select(PaperTrade)).scalars()
    assert trade.quantity == 1_000
    db_session.refresh(row)
    assert row.total_fees == pytest.approx(1.25)
    # Cash identity: allocated − fees − Σ qty × avg_cost = allocated − gross notional.
    cash = row.allocated_capital - row.total_fees - position.quantity * position.avg_cost
    assert cash == pytest.approx(10_000.0 - 500.0)


def test_equity_buy_is_booked_in_full(db_session: Session) -> None:
    row = _ai_session(db_session)

    _book(db_session, row.id, "buy", 10, AssetClass.EQUITY)

    [position] = db_session.execute(select(SessionPosition)).scalars()
    assert position.quantity == 10


def test_capped_full_crypto_exit_leaves_no_dust(db_session: Session) -> None:
    row = _ai_session(db_session)
    _ledger(db_session, row, "ADA-USD", 997.6, 0.5)

    _book(db_session, row.id, "sell", 997.5, AssetClass.CRYPTO)

    assert list(db_session.execute(select(SessionPosition)).scalars()) == []


def test_partial_crypto_sell_keeps_the_rest(db_session: Session) -> None:
    row = _ai_session(db_session)
    _ledger(db_session, row, "ADA-USD", 1_000, 0.5)

    _book(db_session, row.id, "sell", 400, AssetClass.CRYPTO)

    [position] = db_session.execute(select(SessionPosition)).scalars()
    assert position.quantity == pytest.approx(600)


# --- executor ----------------------------------------------------------------------------
def test_full_crypto_exit_sells_the_account_holding() -> None:
    broker = StubBroker(initial_cash=10_000_000.0)
    broker.buy("ADA-USD", 997.5)
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    [result] = executor.execute_close(
        {"ADA-USD": Position(symbol="ADA-USD", quantity=997.5001, avg_cost=0.5)},
        asset_classes={"ADA-USD": AssetClass.CRYPTO},
    )

    assert result.executed is True
    assert result.shares == pytest.approx(997.5)
    left = broker.get_position("ADA-USD")
    assert left is None or left.quantity == pytest.approx(0)


def test_crypto_minimum_matches_the_broker() -> None:
    assert MIN_CRYPTO_NOTIONAL_USD == 10.0


# --- admin write-off ---------------------------------------------------------------------
def test_fee_residue_is_written_off_proportionally(db_session: Session) -> None:
    first = _ai_session(db_session, name="Growth")
    second = _ai_session(db_session, name="Crypto")
    _ledger(db_session, first, "ADA-USD", 600, 0.5)
    _ledger(db_session, second, "ADA-USD", 400, 0.4)
    broker = _crypto_broker(("ADA-USD", 997.5))
    orders_before = len(broker.get_open_orders())

    row = _row(admin_service.account_overview(db_session, broker).positions, "ADA-USD")
    assert (row.write_off_eligible, row.write_off_quantity, row.restorable) == (True, 2.5, False)

    [outcome] = admin_service.write_off_positions(db_session, broker)

    assert (outcome.result, outcome.quantity) == ("written_off", 2.5)
    db_session.expire_all()
    ledgers = {
        p.session_id: (p.quantity, p.avg_cost)
        for p in db_session.execute(select(SessionPosition)).scalars()
    }
    assert ledgers[first.id] == (pytest.approx(598.5), 0.5)
    assert ledgers[second.id] == (pytest.approx(399.0), 0.4)
    assert len(broker.get_open_orders()) == orders_before
    assert db_session.execute(select(BrokerOrder)).first() is None
    after = _row(admin_service.account_overview(db_session, broker).positions, "ADA-USD")
    assert after.status == "matched"


def test_gap_beyond_tolerance_is_not_written_off(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "SOL-USD", 10, 150.0)
    broker = _crypto_broker(("SOL-USD", 9.5))

    row = _row(admin_service.account_overview(db_session, broker).positions, "SOL-USD")
    assert (row.write_off_eligible, row.restorable) == (False, True)
    [outcome] = admin_service.write_off_positions(db_session, broker, symbol="SOL-USD")
    assert (outcome.result, outcome.reason) == ("skipped", "not_eligible")


def test_equity_shortfall_is_never_written_off(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "AAPL", 100, 100.0)
    broker = _broker(("AAPL", 99.5))

    row = _row(admin_service.account_overview(db_session, broker).positions, "AAPL")
    assert row.write_off_eligible is False


def test_tiny_crypto_restore_is_skipped_below_the_minimum(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "SOL-USD", 0.51, 150.0)
    broker = _crypto_broker(("SOL-USD", 0.5))  # 0.01 SOL short of Cadence: ~2%, worth < $10

    [outcome] = admin_service.restore_positions(db_session, broker)

    assert (outcome.result, outcome.reason) == ("skipped", "below_minimum")


# --- admin rejections ------------------------------------------------------------------------
def test_rejected_admin_order_is_closed_at_once(db_session: Session) -> None:
    class _Rejecting(StubBroker):
        def buy(self, *args: object, **kwargs: object) -> Order:  # type: ignore[override]
            raise OrderError("Alpaca API error: cost basis must be >= minimal amount of order 10")

    with pytest.raises(OrderError):
        OrderGateway(_Rejecting(), owner_kind=OrderOwnerKind.ADMIN).buy(
            "SOL-USD", 0.02, purpose="admin_restore", asset_class=AssetClass.CRYPTO
        )

    db_session.expire_all()
    [row] = db_session.execute(select(BrokerOrder)).scalars()
    assert row.state == JournalState.RESOLVED.value
    assert journal.list_unresolved(db_session) == []
    assert admin_service.account_overview(db_session, StubBroker()).unresolved_orders == []
