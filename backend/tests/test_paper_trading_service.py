"""Integration tests for the paper-trading service against Postgres."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from cadence.api.schemas import SessionValueSnapshotRead
from cadence.assets.category import AssetCategory
from cadence.assets.models import Asset
from cadence.assets.sector import Sector
from cadence.broker.models import (
    AssetClass,
    Order,
    OrderSide,
    OrderStatus,
    Quote,
)
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.paper_trading import service
from cadence.paper_trading.benchmark import Contribution
from cadence.paper_trading.constants import (
    SHARPE_MIN_RETURNS,
    Benchmark,
    RunStatus,
    ScheduleMode,
    SessionStatus,
)
from cadence.paper_trading.errors import (
    DuplicateSessionError,
    InvalidAssetScopeError,
    InvalidBenchmarkError,
    InvalidCapitalChangeError,
    SessionNotArchivableError,
    SessionNotFoundError,
)
from cadence.paper_trading.models import (
    BenchmarkPrice,
    PaperTradingSession,
    SessionCapitalEvent,
    SessionValueSnapshot,
)
from cadence.portfolios import service as portfolios_service
from cadence.portfolios.models import Portfolio


def _portfolio(db_session: Session) -> Portfolio:
    return portfolios_service.create_portfolio(
        db_session, name="P", stocks=["AAPL", "MSFT"]
    )


def test_create_session_defaults(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    assert sess.id is not None
    assert sess.portfolio_id == portfolio.id
    assert sess.status == SessionStatus.ACTIVE.value
    assert sess.allocated_capital == 100000.0
    assert sess.schedule_mode == ScheduleMode.SCHEDULED.value
    assert sess.total_trades == 0
    assert sess.total_pnl == 0.0


def test_duplicate_portfolio_strategy_raises(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    with pytest.raises(DuplicateSessionError):
        service.create_session(
            db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)


def test_get_and_not_found(db_session: Session) -> None:
    import uuid

    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    assert service.get_session(db_session, sess.id).id == sess.id
    with pytest.raises(SessionNotFoundError):
        service.get_session(db_session, uuid.uuid4())


def test_record_trade_derives_notional(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    trade = service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=25.0,
        signal_type="entry",
        asset_class=AssetClass.EQUITY,
        order_status=OrderStatus.FILLED,
    )
    assert trade.notional == 250.0
    assert trade.side == OrderSide.BUY.value
    assert trade.order_status == OrderStatus.FILLED.value
    assert service.count_session_trades(db_session, sess.id) == 1


def test_record_trade_equity_charges_no_fee(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    # A fresh session starts fee-free.
    assert sess.total_fees == pytest.approx(0.0)
    for _ in range(2):
        service.record_trade(
            db_session,
            session_id=sess.id,
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            price=10.0,
            signal_type="entry",
            asset_class=AssetClass.EQUITY,
        )
    # Equities trade commission-free on Alpaca — no fee accrues.
    refreshed = service.get_session(db_session, sess.id)
    assert refreshed.total_fees == pytest.approx(0.0)


def test_record_trade_crypto_charges_pct_of_notional(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CRYPTO_FEE_PCT", 0.0025)
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    # Two crypto trades each accrue pct × notional (filled price when present).
    service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="BTC-USD",
        side=OrderSide.BUY,
        quantity=2.0,
        price=100.0,
        signal_type="entry",
        asset_class=AssetClass.CRYPTO,
    )
    service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.0,
        price=100.0,
        filled_price=200.0,
        signal_type="entry",
        asset_class=AssetClass.CRYPTO,
    )
    refreshed = service.get_session(db_session, sess.id)
    # 0.0025 * (2 * 100) + 0.0025 * (1 * 200) = 0.5 + 0.5 = 1.0.
    assert refreshed.total_fees == pytest.approx(0.0025 * 200.0 + 0.0025 * 200.0)


def test_record_run(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    run = service.record_session_run(
        db_session,
        session_id=sess.id,
        signals_scanned=5,
        signals_actionable=2,
        orders_executed=1,
        orders_skipped=1,
        details=[{"ticker": "AAPL", "action": "buy"}],
        status=RunStatus.SUCCESS,
        run_trigger="manual",
        duration_ms=123,
    )
    assert run.signals_scanned == 5
    assert run.status == RunStatus.SUCCESS.value
    assert run.run_trigger == "manual"
    assert run.details == [{"ticker": "AAPL", "action": "buy"}]
    assert service.count_session_runs(db_session, sess.id) == 1


def test_record_closed_position_computes_pnl(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    entry = datetime(2026, 1, 1, tzinfo=UTC)
    exit_ = entry + timedelta(days=10)
    pos = service.record_closed_position(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        quantity=10,
        entry_price=100.0,
        exit_price=110.0,
        entry_date=entry,
        exit_date=exit_,
    )
    assert pos.realized_pnl == pytest.approx(100.0)
    assert pos.return_pct == pytest.approx(0.1)
    assert pos.holding_days == 10
    assert service.count_closed_positions(db_session, sess.id) == 1


def test_update_last_run_and_status(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    updated = service.update_session_last_run(
        db_session, sess.id, trades_delta=3, pnl_delta=42.5
    )
    assert updated.total_trades == 3
    assert updated.total_pnl == pytest.approx(42.5)
    assert updated.last_run_at is not None

    paused = service.update_session_status(
        db_session, sess.id, SessionStatus.PAUSED
    )
    assert paused.status == SessionStatus.PAUSED.value


def test_list_sessions_filter_by_status(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    active = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="a", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    stopped = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="b", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    service.update_session_status(db_session, stopped.id, SessionStatus.STOPPED)

    active_ids = [
        s.id for s in service.list_sessions(db_session, status=SessionStatus.ACTIVE)
    ]
    assert active.id in active_ids
    assert stopped.id not in active_ids


# --------------------------------------------------------------------------- #
# Archiving
# --------------------------------------------------------------------------- #


def _stopped_session(db_session: Session, strategy_key: str = "s") -> object:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key=strategy_key, rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    return service.update_session_status(
        db_session, sess.id, SessionStatus.STOPPED
    )


def test_archive_stopped_session_sets_timestamp(db_session: Session) -> None:
    sess = _stopped_session(db_session)
    archived = service.archive_session(db_session, sess.id)
    assert archived.archived_at is not None
    # Archiving does not change status.
    assert archived.status == SessionStatus.STOPPED.value


def test_archive_rejects_active_or_paused(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    active = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="a", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    with pytest.raises(SessionNotArchivableError):
        service.archive_session(db_session, active.id)

    service.update_session_status(db_session, active.id, SessionStatus.PAUSED)
    with pytest.raises(SessionNotArchivableError):
        service.archive_session(db_session, active.id)


def test_unarchive_clears_timestamp(db_session: Session) -> None:
    sess = _stopped_session(db_session)
    service.archive_session(db_session, sess.id)
    restored = service.unarchive_session(db_session, sess.id)
    assert restored.archived_at is None


def test_default_list_hides_archived(db_session: Session) -> None:
    sess = _stopped_session(db_session)
    service.archive_session(db_session, sess.id)

    visible_ids = [s.id for s in service.list_sessions(db_session)]
    assert sess.id not in visible_ids
    assert service.count_sessions(db_session) == 0

    with_archived = [
        s.id for s in service.list_sessions(db_session, include_archived=True)
    ]
    assert sess.id in with_archived
    assert service.count_sessions(db_session, include_archived=True) == 1


def test_archive_unknown_session_raises(db_session: Session) -> None:
    import uuid

    with pytest.raises(SessionNotFoundError):
        service.archive_session(db_session, uuid.uuid4())
    with pytest.raises(SessionNotFoundError):
        service.unarchive_session(db_session, uuid.uuid4())


# --------------------------------------------------------------------------- #
# Open-position ledger
# --------------------------------------------------------------------------- #


def _ledger_session(db_session: Session) -> object:
    portfolio = _portfolio(db_session)
    return service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="ledger", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)


def test_apply_fill_to_ledger_opens_and_averages_up(db_session: Session) -> None:
    sess = _ledger_session(db_session)

    # First buy opens the entry at the fill price.
    entry = service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=100.0,
    )
    assert entry is not None
    assert entry.quantity == pytest.approx(10)
    assert entry.avg_cost == pytest.approx(100.0)

    # Second buy increases quantity and re-computes the weighted-average cost:
    # (10*100 + 10*120) / 20 = 110.
    entry = service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=120.0,
    )
    assert entry is not None
    assert entry.quantity == pytest.approx(20)
    assert entry.avg_cost == pytest.approx(110.0)


def test_apply_fill_to_ledger_partial_sell_then_full_exit(db_session: Session) -> None:
    sess = _ledger_session(db_session)
    service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=100.0,
    )

    # Partial sell reduces quantity, leaving the weighted-average cost unchanged.
    entry = service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.SELL,
        shares=4,
        price=130.0,
    )
    assert entry is not None
    assert entry.quantity == pytest.approx(6)
    assert entry.avg_cost == pytest.approx(100.0)

    # Full exit removes the row entirely.
    removed = service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.SELL,
        shares=6,
        price=130.0,
    )
    assert removed is None
    assert service.get_open_position(db_session, sess.id, "AAPL") is None


def test_list_open_positions_scoped_to_session(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    a = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="a", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    b = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="b", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    service.apply_fill_to_ledger(
        db_session, session_id=a.id, ticker="AAPL", side=OrderSide.BUY,
        shares=5, price=50.0,
    )
    service.apply_fill_to_ledger(
        db_session, session_id=a.id, ticker="MSFT", side=OrderSide.BUY,
        shares=3, price=40.0,
    )
    service.apply_fill_to_ledger(
        db_session, session_id=b.id, ticker="AAPL", side=OrderSide.BUY,
        shares=8, price=90.0,
    )

    a_positions = service.list_open_positions(db_session, a.id)
    assert {p.ticker for p in a_positions} == {"AAPL", "MSFT"}
    # The same ticker in another session tracks its own independent quantity/cost.
    a_aapl = service.get_open_position(db_session, a.id, "AAPL")
    b_aapl = service.get_open_position(db_session, b.id, "AAPL")
    assert a_aapl is not None and a_aapl.quantity == pytest.approx(5)
    assert b_aapl is not None and b_aapl.quantity == pytest.approx(8)


def test_get_position_entry_basis_is_pre_sell(db_session: Session) -> None:
    sess = _ledger_session(db_session)
    opened = service.apply_fill_to_ledger(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        shares=10, price=100.0,
    )
    service.apply_fill_to_ledger(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        shares=10, price=120.0,
    )
    assert opened is not None

    basis = service.get_position_entry_basis(db_session, sess.id, "AAPL")
    assert basis is not None
    avg_cost, opened_at = basis
    # Basis reflects the weighted-average cost (110) and the original opened date.
    assert avg_cost == pytest.approx(110.0)
    assert opened_at == opened.opened_at

    assert service.get_position_entry_basis(db_session, sess.id, "NONE") is None


# --------------------------------------------------------------------------- #
# Order-status reconciliation
# --------------------------------------------------------------------------- #


class _OrderBroker:
    """Broker double that returns pre-seeded orders keyed by order id.

    ``orders`` maps order_id -> ``Order`` (the broker's current view). An order_id
    mapped to ``None`` simulates an order the broker no longer knows about; an
    order_id listed in ``raises`` makes ``get_order`` blow up for that id (the
    transient-failure path).
    """

    def __init__(
        self,
        orders: dict[str, Order | None],
        *,
        raises: set[str] | None = None,
    ) -> None:
        self._orders = orders
        self._raises = raises or set()

    def get_order(self, order_id: str) -> Order | None:
        if order_id in self._raises:
            raise RuntimeError("get_order boom")
        return self._orders.get(order_id)


def _filled_order(
    ticker: str,
    side: OrderSide,
    qty: float,
    price: float,
    *,
    order_id: str,
) -> Order:
    return Order(
        symbol=ticker,
        side=side,
        quantity=qty,
        asset_class=AssetClass.EQUITY,
        order_id=order_id,
        status=OrderStatus.FILLED,
        filled_quantity=qty,
        filled_price=price,
        filled_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def test_reconcile_updates_nonterminal_buy_to_filled(db_session: Session) -> None:
    sess = _ai_session(db_session)
    service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=100.0,
        signal_type="entry",
        asset_class=AssetClass.EQUITY,
        order_id="o1",
        order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {"o1": _filled_order("AAPL", OrderSide.BUY, 10, 100.0, order_id="o1")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    assert result.trades_seen == 1
    assert result.trades_reconciled == 1
    assert result.trades_filled == 1

    (trade,) = service.get_session_trades(db_session, sess.id)
    assert trade.order_status == OrderStatus.FILLED.value
    assert trade.filled_price == pytest.approx(100.0)
    assert trade.filled_at is not None


def test_reconcile_leaves_terminal_and_orderless_trades_untouched(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    # Already terminal — never re-queried.
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=1, price=10.0, signal_type="entry", asset_class=AssetClass.EQUITY,
        order_id="done", order_status=OrderStatus.FILLED,
    )
    # No broker order id — nothing to reconcile against.
    service.record_trade(
        db_session, session_id=sess.id, ticker="MSFT", side=OrderSide.BUY,
        quantity=1, price=20.0, signal_type="entry", asset_class=AssetClass.EQUITY,
        order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {"done": _filled_order("AAPL", OrderSide.BUY, 1, 999.0, order_id="done")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    assert result.trades_seen == 0
    assert result.trades_reconciled == 0


def test_reconcile_skips_missing_or_failing_order_and_continues(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=1, price=10.0, signal_type="entry", asset_class=AssetClass.EQUITY,
        order_id="gone", order_status=OrderStatus.SUBMITTED,
    )
    service.record_trade(
        db_session, session_id=sess.id, ticker="MSFT", side=OrderSide.BUY,
        quantity=1, price=20.0, signal_type="entry", asset_class=AssetClass.EQUITY,
        order_id="boom", order_status=OrderStatus.SUBMITTED,
    )
    service.record_trade(
        db_session, session_id=sess.id, ticker="NVDA", side=OrderSide.BUY,
        quantity=1, price=30.0, signal_type="entry", asset_class=AssetClass.EQUITY,
        order_id="ok", order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {
            "gone": None,  # broker no longer knows this order
            "ok": _filled_order("NVDA", OrderSide.BUY, 1, 30.0, order_id="ok"),
        },
        raises={"boom"},
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    # All three seen; only the healthy one reconciled — the batch never aborts.
    assert result.trades_seen == 3
    assert result.trades_reconciled == 1
    assert result.trades_filled == 1


def test_reconcile_corrects_ledger_cost_basis_on_price_delta(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    # Open the ledger at the estimated fill price, then record the pending trade.
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=10, price=100.0, signal_type="entry", asset_class=AssetClass.EQUITY,
        order_id="o1", order_status=OrderStatus.SUBMITTED,
    )
    # Broker reports the actual fill at 105 -> +5/share correction over 10 shares.
    broker = _OrderBroker(
        {"o1": _filled_order("AAPL", OrderSide.BUY, 10, 105.0, order_id="o1")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    assert result.trades_basis_corrected == 1

    entry = service.get_open_position(db_session, sess.id, "AAPL")
    assert entry is not None
    # avg_cost = 100 + (5 * 10) / 10 = 105.
    assert entry.avg_cost == pytest.approx(105.0)


def test_reconcile_equal_fill_price_is_noop_for_ledger(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=10, price=100.0, signal_type="entry", asset_class=AssetClass.EQUITY,
        order_id="o1", order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {"o1": _filled_order("AAPL", OrderSide.BUY, 10, 100.0, order_id="o1")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    assert result.trades_basis_corrected == 0
    entry = service.get_open_position(db_session, sess.id, "AAPL")
    assert entry is not None
    assert entry.avg_cost == pytest.approx(100.0)


def test_reconcile_price_delta_on_closed_position_skips_ledger(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    # A pending buy whose position never opened (or was already fully sold).
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=10, price=100.0, signal_type="entry", asset_class=AssetClass.EQUITY,
        order_id="o1", order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {"o1": _filled_order("AAPL", OrderSide.BUY, 10, 105.0, order_id="o1")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    # Trade still reconciled, but no open ledger entry to correct.
    assert result.trades_reconciled == 1
    assert result.trades_basis_corrected == 0
    assert service.get_open_position(db_session, sess.id, "AAPL") is None


def test_reconcile_unknown_session_raises(db_session: Session) -> None:
    import uuid

    with pytest.raises(SessionNotFoundError):
        service.reconcile_session_orders(db_session, _OrderBroker({}), uuid.uuid4())


# --------------------------------------------------------------------------- #
# Portfolio-value snapshots
# --------------------------------------------------------------------------- #


class _QuoteBroker:
    """Minimal broker double that prices the tickers it is configured with.

    ``prices`` maps ticker -> price. A ticker mapped to ``None`` yields a quote
    with no usable price (exercises the avg-cost fallback); a ticker absent from
    the map is omitted from the result entirely (a missing symbol). ``raises``
    makes ``get_quotes`` blow up wholesale (the total quote-fetch failure path).
    """

    def __init__(
        self, prices: dict[str, float | None], *, raises: bool = False
    ) -> None:
        self._prices = prices
        self._raises = raises

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        if self._raises:
            raise RuntimeError("quote boom")
        out: dict[str, Quote] = {}
        for sym in symbols:
            if sym not in self._prices:
                continue
            price = self._prices[sym]
            if price is None:
                out[sym] = Quote(symbol=sym)
            else:
                out[sym] = Quote(symbol=sym, bid=price, ask=price, last=price)
        return out


def _ai_session(db_session: Session) -> object:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="AI", stocks=["AAPL", "MSFT"]
    )
    return service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_buy_hold",
        allocated_capital=100_000.0, rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)


def _buy(db_session: Session, session_id: object, ticker: str, qty: float, price: float) -> None:
    service.apply_fill_to_ledger(
        db_session,
        session_id=session_id,
        ticker=ticker,
        side=OrderSide.BUY,
        shares=qty,
        price=price,
    )


def test_compute_value_all_cash(db_session: Session) -> None:
    sess = _ai_session(db_session)
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    # No holdings -> equity is exactly the seed capital, all in cash.
    assert valuation.total_value == pytest.approx(100_000.0)
    assert valuation.positions_value == pytest.approx(0.0)
    assert valuation.cash_value == pytest.approx(100_000.0)
    assert valuation.positions == []


def test_compute_value_marked_up_holding(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # cost basis 1000
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    # +20/share on 10 shares = +200 unrealized.
    assert valuation.positions_value == pytest.approx(1200.0)
    assert valuation.total_value == pytest.approx(100_200.0)
    assert valuation.cash_value == pytest.approx(99_000.0)
    (pos,) = valuation.positions
    assert pos["ticker"] == "AAPL"
    assert pos["market_value"] == pytest.approx(1200.0)
    assert pos["unrealized_pnl"] == pytest.approx(200.0)
    assert pos["return_pct"] == pytest.approx(0.2)


def test_compute_value_marked_down_holding(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 80.0})
    )
    assert valuation.positions_value == pytest.approx(800.0)
    assert valuation.total_value == pytest.approx(99_800.0)
    (pos,) = valuation.positions
    assert pos["unrealized_pnl"] == pytest.approx(-200.0)
    assert pos["return_pct"] == pytest.approx(-0.2)


def test_compute_value_quote_failure_isolated_to_one_ticker(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # priced 120 -> +200
    _buy(db_session, sess.id, "MSFT", 5, 50.0)  # no usable quote -> avg cost
    valuation = service.compute_session_value(
        db_session,
        session_id=sess.id,
        broker=_QuoteBroker({"AAPL": 120.0, "MSFT": None}),
    )
    by_ticker = {p["ticker"]: p for p in valuation.positions}
    # AAPL marked up as normal; MSFT falls back to its avg cost (flat, no P&L).
    assert by_ticker["AAPL"]["unrealized_pnl"] == pytest.approx(200.0)
    assert by_ticker["MSFT"]["price"] == pytest.approx(50.0)
    assert by_ticker["MSFT"]["unrealized_pnl"] == pytest.approx(0.0)
    # AAPL 1200 + MSFT 250 = 1450 of positions value; +200 total P&L.
    assert valuation.positions_value == pytest.approx(1450.0)
    assert valuation.total_value == pytest.approx(100_200.0)


def test_compute_value_total_quote_failure_falls_back_to_cost(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({}, raises=True)
    )
    # A wholesale get_quotes failure values every holding at avg cost (flat).
    assert valuation.positions_value == pytest.approx(1000.0)
    assert valuation.total_value == pytest.approx(100_000.0)


def test_record_snapshot_is_idempotent_per_day(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    broker = _QuoteBroker({"AAPL": 100.0})
    day = date(2026, 1, 5)

    first = service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=day, broker=broker
    )
    second = service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=day, broker=broker
    )
    # Two runs for the same day update one row (same id), never insert twice.
    assert first.id == second.id
    assert len(service.list_value_snapshots(db_session, session_id=sess.id)) == 1
    # No prior snapshot -> baseline is the allocated capital (flat -> zero P&L).
    assert second.daily_pnl == pytest.approx(0.0)
    assert second.daily_pnl_pct == pytest.approx(0.0)


def test_record_snapshot_daily_pnl_uses_prior(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)

    # Day 1: flat at cost -> total == allocated, baseline == allocated.
    day1 = service.record_value_snapshot(
        db_session,
        session_id=sess.id,
        as_of=date(2026, 1, 5),
        broker=_QuoteBroker({"AAPL": 100.0}),
    )
    assert day1.total_value == pytest.approx(100_000.0)

    # Day 2: marked up to 120 -> +200 vs the prior day's total_value.
    day2 = service.record_value_snapshot(
        db_session,
        session_id=sess.id,
        as_of=date(2026, 1, 6),
        broker=_QuoteBroker({"AAPL": 120.0}),
    )
    assert day2.total_value == pytest.approx(100_200.0)
    assert day2.daily_pnl == pytest.approx(200.0)
    assert day2.daily_pnl_pct == pytest.approx(200.0 / 100_000.0)


def test_list_value_snapshots_ascending(db_session: Session) -> None:
    sess = _ai_session(db_session)
    broker = _QuoteBroker({})
    for day in (date(2026, 1, 6), date(2026, 1, 4), date(2026, 1, 5)):
        service.record_value_snapshot(
            db_session, session_id=sess.id, as_of=day, broker=broker
        )
    dates = [
        s.snapshot_date
        for s in service.list_value_snapshots(db_session, session_id=sess.id)
    ]
    assert dates == [date(2026, 1, 4), date(2026, 1, 5), date(2026, 1, 6)]


def test_sessions_value_comparison_shapes_series(db_session: Session) -> None:
    broker = _QuoteBroker({})

    # Session A: two snapshots on distinct days (should come back oldest-first).
    sess_a = _ai_session(db_session)
    for day in (date(2026, 1, 6), date(2026, 1, 4)):
        service.record_value_snapshot(
            db_session, session_id=sess_a.id, as_of=day, broker=broker
        )

    # Session B: no snapshots yet -> included with an empty points list.
    sess_b = _ai_session(db_session)

    # Session C: archived -> excluded from the comparison entirely.
    sess_c = _ai_session(db_session)
    service.record_value_snapshot(
        db_session, session_id=sess_c.id, as_of=date(2026, 1, 5), broker=broker
    )
    service.update_session_status(db_session, sess_c.id, SessionStatus.STOPPED)
    service.archive_session(db_session, sess_c.id)

    series = service.list_sessions_value_comparison(db_session)
    by_id = {s.session_id: s for s in series}

    # Archived session excluded; the two non-archived ones are present.
    assert sess_c.id not in by_id
    assert set(by_id) == {sess_a.id, sess_b.id}

    # Session A carries its points oldest date first, with label + capital.
    a = by_id[sess_a.id]
    assert a.label == "AI"
    assert a.allocated_capital == pytest.approx(100_000.0)
    assert [p.snapshot_date for p in a.points] == [
        date(2026, 1, 4),
        date(2026, 1, 6),
    ]

    # Session B has no snapshots -> empty points, still labelled + capitalised.
    b = by_id[sess_b.id]
    assert b.label == "AI"
    assert b.points == []


def test_snapshot_row_validates_into_read_schema(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    row = service.record_value_snapshot(
        db_session,
        session_id=sess.id,
        as_of=date(2026, 1, 5),
        broker=_QuoteBroker({"AAPL": 120.0}),
    )
    read = SessionValueSnapshotRead.model_validate(row)
    assert read.snapshot_date == date(2026, 1, 5)
    assert read.total_value == pytest.approx(100_200.0)
    assert read.positions[0]["ticker"] == "AAPL"


def test_compute_value_surfaces_unrealized_pnl(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +20/share -> +200
    _buy(db_session, sess.id, "MSFT", 5, 50.0)  # -10/share -> -50
    valuation = service.compute_session_value(
        db_session,
        session_id=sess.id,
        broker=_QuoteBroker({"AAPL": 120.0, "MSFT": 40.0}),
    )
    # Top-level unrealised P&L equals the sum of the per-position marks.
    per_position = sum(p["unrealized_pnl"] for p in valuation.positions)
    assert valuation.unrealized_pnl == pytest.approx(150.0)
    assert valuation.unrealized_pnl == pytest.approx(per_position)


# --------------------------------------------------------------------------- #
# Sharpe ratio (pure helper)
# --------------------------------------------------------------------------- #


def test_sharpe_ratio_known_series() -> None:
    returns = [0.01] * 10 + [0.02] * 10  # 20 observations, non-zero variance
    assert service.sharpe_ratio(returns) == pytest.approx(46.417669, abs=1e-4)


def test_sharpe_ratio_none_below_minimum() -> None:
    returns = [0.01, -0.01] * ((SHARPE_MIN_RETURNS - 1) // 2)
    assert len(returns) < SHARPE_MIN_RETURNS
    assert service.sharpe_ratio(returns) is None


def test_sharpe_ratio_none_when_flat() -> None:
    # Enough observations but zero standard deviation -> no signal, no divide-by-zero.
    assert service.sharpe_ratio([0.01] * SHARPE_MIN_RETURNS) is None


def test_sharpe_ratio_excess_over_risk_free() -> None:
    returns = [0.01] * 10 + [0.02] * 10
    # A positive risk-free rate lowers the numerator, hence the ratio.
    assert service.sharpe_ratio(returns, risk_free=0.001) < service.sharpe_ratio(
        returns
    )


# --------------------------------------------------------------------------- #
# Session KPIs
# --------------------------------------------------------------------------- #


def _add_snapshot(
    db_session: Session, session_id: object, day: date, daily_pnl_pct: float
) -> None:
    """Insert a minimal value snapshot carrying a daily return for Sharpe tests."""
    db_session.add(
        SessionValueSnapshot(
            session_id=session_id,
            snapshot_date=day,
            total_value=0.0,
            cash_value=0.0,
            positions_value=0.0,
            daily_pnl=0.0,
            daily_pnl_pct=daily_pnl_pct,
            positions=[],
        )
    )
    db_session.commit()


def test_session_kpis_live_figures_and_total_return(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +20/share -> +200 unrealised
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    assert kpis.current_value == pytest.approx(100_200.0)
    # Unallocated cash is the live value minus the marked-to-market positions value
    # (10 shares @ $120 = $1,200): 100,000 allocated − 1,000 spent = 99,000 cash.
    assert kpis.unallocated_cash == pytest.approx(99_000.0)
    assert kpis.unallocated_cash == pytest.approx(kpis.current_value - 1_200.0)
    assert kpis.realised_pnl == pytest.approx(0.0)
    assert kpis.unrealised_pnl == pytest.approx(200.0)
    # Total return, absolute and fractional, vs the 100k allocated capital.
    assert kpis.total_return == pytest.approx(200.0)
    assert kpis.total_return == pytest.approx(kpis.realised_pnl + kpis.unrealised_pnl)
    assert kpis.total_return_pct == pytest.approx(200.0 / 100_000.0)
    # No snapshots yet -> Sharpe not yet available.
    assert kpis.sharpe_ratio is None


def test_session_kpis_net_of_fees_and_gross_realised(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CRYPTO_FEE_PCT", 0.0025)
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +20/share -> +200 unrealised
    # Two crypto trades accrue percentage transaction fees on the session.
    for _ in range(2):
        service.record_trade(
            db_session,
            session_id=sess.id,
            ticker="BTC-USD",
            side=OrderSide.BUY,
            quantity=1,
            price=100.0,
            signal_type="entry",
            asset_class=AssetClass.CRYPTO,
        )
    fees = 2 * 0.0025 * 100.0  # pct × notional per crypto trade
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    # Current value is net of fees; total_fees is surfaced.
    assert kpis.total_fees == pytest.approx(fees)
    assert kpis.current_value == pytest.approx(100_200.0 - fees)
    assert kpis.total_return == pytest.approx(200.0 - fees)
    # Realised P&L stays gross (fees are tracked separately, not folded in).
    assert kpis.realised_pnl == pytest.approx(0.0)


def test_session_kpis_daily_avg_orders(db_session: Session) -> None:
    sess = _ai_session(db_session)
    for _ in range(3):
        service.record_trade(
            db_session,
            session_id=sess.id,
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            price=10.0,
            signal_type="entry",
            asset_class=AssetClass.EQUITY,
        )
    base = date(2026, 1, 1)
    for i in range(4):  # four recorded snapshot days
        _add_snapshot(db_session, sess.id, base + timedelta(days=i), 0.0)
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 10.0})
    )
    # Recorded orders spread over the number of snapshot days (3 / 4).
    assert kpis.daily_avg_orders == pytest.approx(3 / 4)


def test_session_kpis_daily_avg_orders_none_without_snapshots(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=1,
        price=10.0,
        signal_type="entry",
        asset_class=AssetClass.EQUITY,
    )
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 10.0})
    )
    # No snapshots yet -> daily average is not yet available (no divide-by-zero).
    assert kpis.daily_avg_orders is None


def test_session_kpis_sharpe_none_until_enough_history(db_session: Session) -> None:
    sess = _ai_session(db_session)
    base = date(2026, 1, 1)
    for i in range(SHARPE_MIN_RETURNS - 1):  # one short of the minimum
        _add_snapshot(db_session, sess.id, base + timedelta(days=i), 0.01 + 0.001 * i)
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    assert kpis.sharpe_ratio is None


def test_session_kpis_sharpe_from_snapshot_series(db_session: Session) -> None:
    sess = _ai_session(db_session)
    base = date(2026, 1, 1)
    # KPIs recompute the daily return series from snapshot NAVs (not the stored
    # daily_pnl_pct), so build a NAV series that yields returns [0.01]*10 + [0.02]*10
    # against the 100k baseline contributed capital.
    returns = [0.01] * 10 + [0.02] * 10
    value = 100_000.0
    for i, ret in enumerate(returns):
        value *= 1.0 + ret
        _add_value_snapshot(db_session, sess.id, base + timedelta(days=i), value)
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    assert kpis.sharpe_ratio == pytest.approx(46.417669, abs=1e-4)


def test_session_kpis_unknown_session_raises(db_session: Session) -> None:
    import uuid

    with pytest.raises(SessionNotFoundError):
        service.session_kpis(
            db_session, session_id=uuid.uuid4(), broker=_QuoteBroker({})
        )


# --------------------------------------------------------------------------- #
# Max drawdown (pure helper)
# --------------------------------------------------------------------------- #


def test_max_drawdown_rise_then_fall() -> None:
    # Peak 120, trough 90 -> (120-90)/120 = 0.25, despite a later partial recovery.
    assert service.max_drawdown([100, 120, 90, 105]) == pytest.approx(0.25)


def test_max_drawdown_monotonic_rise_is_zero() -> None:
    assert service.max_drawdown([100, 110, 130]) == pytest.approx(0.0)


def test_max_drawdown_empty_is_none() -> None:
    assert service.max_drawdown([]) is None


def test_max_drawdown_non_positive_peak_contributes_nothing() -> None:
    # A zero/negative running peak is guarded (no divide-by-zero), yielding 0.0.
    assert service.max_drawdown([0.0, 0.0]) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Closed-position stats (pure helper)
# --------------------------------------------------------------------------- #


def test_closed_position_stats_mixed() -> None:
    stats = service.closed_position_stats([100.0, -40.0, 60.0, -20.0])
    assert stats.win_rate == pytest.approx(0.5)  # 2 of 4 positive
    assert stats.average_win == pytest.approx(80.0)  # mean(100, 60)
    assert stats.average_loss == pytest.approx(-30.0)  # mean(-40, -20)
    assert stats.best_trade == pytest.approx(100.0)
    assert stats.worst_trade == pytest.approx(-40.0)


def test_closed_position_stats_empty_all_none() -> None:
    stats = service.closed_position_stats([])
    assert stats.win_rate is None
    assert stats.average_win is None
    assert stats.average_loss is None
    assert stats.best_trade is None
    assert stats.worst_trade is None


def test_closed_position_stats_all_winners_has_no_average_loss() -> None:
    stats = service.closed_position_stats([10.0, 20.0])
    assert stats.win_rate == pytest.approx(1.0)
    assert stats.average_win == pytest.approx(15.0)
    assert stats.average_loss is None
    assert stats.best_trade == pytest.approx(20.0)
    assert stats.worst_trade == pytest.approx(10.0)


def test_closed_position_stats_all_losers_has_no_average_win() -> None:
    stats = service.closed_position_stats([-10.0, -20.0])
    assert stats.win_rate == pytest.approx(0.0)
    assert stats.average_win is None
    assert stats.average_loss == pytest.approx(-15.0)
    assert stats.best_trade == pytest.approx(-10.0)
    assert stats.worst_trade == pytest.approx(-20.0)


def _add_value_snapshot(
    db_session: Session, session_id: object, day: date, total_value: float
) -> None:
    """Insert a value snapshot carrying a NAV total for drawdown tests."""
    db_session.add(
        SessionValueSnapshot(
            session_id=session_id,
            snapshot_date=day,
            total_value=total_value,
            cash_value=total_value,
            positions_value=0.0,
            daily_pnl=0.0,
            daily_pnl_pct=0.0,
            positions=[],
        )
    )
    db_session.commit()


def _close_position(
    db_session: Session, session_id: object, ticker: str, realized: float
) -> None:
    """Record a closed position whose realized P&L equals ``realized``."""
    service.record_closed_position(
        db_session,
        session_id=session_id,
        ticker=ticker,
        quantity=1.0,
        entry_price=100.0,
        exit_price=100.0 + realized,  # (exit - entry) * 1 == realized
        entry_date=datetime(2026, 1, 1, tzinfo=UTC),
        exit_date=datetime(2026, 1, 5, tzinfo=UTC),
    )


def test_session_kpis_drawdown_and_trade_metrics(db_session: Session) -> None:
    sess = _ai_session(db_session)
    base = date(2026, 1, 1)
    for i, value in enumerate([100_000.0, 110_000.0, 88_000.0, 99_000.0]):
        _add_value_snapshot(db_session, sess.id, base + timedelta(days=i), value)
    _close_position(db_session, sess.id, "AAA", 100.0)
    _close_position(db_session, sess.id, "BBB", -40.0)
    _close_position(db_session, sess.id, "CCC", 60.0)

    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    # Deepest drop: 110k -> 88k = 0.2.
    assert kpis.max_drawdown == pytest.approx(0.2)
    assert kpis.win_rate == pytest.approx(2 / 3)
    assert kpis.average_win == pytest.approx(80.0)
    assert kpis.average_loss == pytest.approx(-40.0)
    assert kpis.best_trade == pytest.approx(100.0)
    assert kpis.worst_trade == pytest.approx(-40.0)


def test_session_kpis_new_metrics_none_without_data(db_session: Session) -> None:
    sess = _ai_session(db_session)  # no snapshots, no closed positions
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    assert kpis.max_drawdown is None
    assert kpis.win_rate is None
    assert kpis.average_win is None
    assert kpis.average_loss is None
    assert kpis.best_trade is None
    assert kpis.worst_trade is None


def test_portfolio_name_resolves_from_linked_portfolio(
    db_session: Session,
) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_buy_hold",
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
    )
    assert service.get_session(db_session, sess.id).portfolio_name == "P"


def test_portfolio_name_is_none_when_portfolio_unresolved() -> None:
    # A session with no linked portfolio (transient) surfaces None rather than
    # raising, so callers can fall back to the strategy label.
    assert PaperTradingSession().portfolio_name is None


# --------------------------------------------------------------------------- #
# Benchmark: change selection, value-history overlay, KPI comparison
# --------------------------------------------------------------------------- #


def _add_benchmark_price(
    db_session: Session, benchmark: str, day: date, close: float
) -> None:
    db_session.add(
        BenchmarkPrice(benchmark=benchmark, price_date=day, close=close)
    )
    db_session.commit()


def test_change_session_benchmark_persists(db_session: Session) -> None:
    sess = _ai_session(db_session)
    updated = service.change_session_benchmark(
        db_session, session_id=sess.id, benchmark="DJIA"
    )
    assert updated.benchmark == "DJIA"
    assert service.get_session(db_session, sess.id).benchmark == "DJIA"


def test_change_session_benchmark_unknown_session_raises(
    db_session: Session,
) -> None:
    import uuid

    with pytest.raises(SessionNotFoundError):
        service.change_session_benchmark(
            db_session, session_id=uuid.uuid4(), benchmark="DJIA"
        )


def test_change_session_benchmark_invalid_id_raises_and_keeps_current(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    with pytest.raises(InvalidBenchmarkError):
        service.change_session_benchmark(
            db_session, session_id=sess.id, benchmark="NOPE"
        )
    # The invalid attempt leaves the original benchmark untouched.
    assert service.get_session(db_session, sess.id).benchmark == Benchmark.SP500.value


class _BoomBroker:
    """Broker double that fails on any interaction.

    Used to prove a scope change that liquidates nothing (a widening or a no-op)
    never touches the broker.
    """

    def get_account_info(self) -> object:
        raise AssertionError("broker must not be called")

    def get_quote(
        self, symbol: str, asset_class: AssetClass = AssetClass.EQUITY
    ) -> Quote:
        raise AssertionError("broker must not be called")

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        raise AssertionError("broker must not be called")

    def sell(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("broker must not be called")


def _set_scope(db_session: Session, session_id: object, scope: str) -> None:
    """Directly seed a session's stored asset scope (bypassing liquidation)."""
    row = service.get_session(db_session, session_id)
    metadata = dict(row.session_metadata or {})
    metadata["asset_types"] = scope
    row.session_metadata = metadata
    db_session.commit()


def test_change_session_scope_persists(db_session: Session) -> None:
    sess = _ai_session(db_session)  # no stored scope -> defaults to "both"
    updated = service.change_session_scope(
        db_session, session_id=sess.id, scope="stocks", broker=StubBroker()
    )
    assert (updated.session_metadata or {})["asset_types"] == "stocks"
    row = service.get_session(db_session, sess.id)
    assert (row.session_metadata or {})["asset_types"] == "stocks"


def test_change_session_scope_unknown_session_raises(db_session: Session) -> None:
    with pytest.raises(SessionNotFoundError):
        service.change_session_scope(
            db_session, session_id=uuid.uuid4(), scope="stocks", broker=_BoomBroker()
        )


def test_change_session_scope_invalid_value_raises_and_keeps_current(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _set_scope(db_session, sess.id, "crypto")
    with pytest.raises(InvalidAssetScopeError) as excinfo:
        service.change_session_scope(
            db_session, session_id=sess.id, scope="nonsense", broker=_BoomBroker()
        )
    # The message lists the allowed scopes, and the stored scope is untouched.
    assert "stocks" in str(excinfo.value) and "both" in str(excinfo.value)
    row = service.get_session(db_session, sess.id)
    assert (row.session_metadata or {})["asset_types"] == "crypto"


def test_change_session_scope_unchanged_is_noop_and_touches_no_broker(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _set_scope(db_session, sess.id, "both")
    # Same scope: a no-op that never reaches the liquidation path (so _BoomBroker
    # is never called).
    updated = service.change_session_scope(
        db_session, session_id=sess.id, scope="both", broker=_BoomBroker()
    )
    assert (updated.session_metadata or {})["asset_types"] == "both"


def test_change_session_scope_widening_sells_nothing(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _set_scope(db_session, sess.id, "stocks")
    _asset(db_session, "AAPL", AssetCategory.STOCK)
    _buy(db_session, sess.id, "AAPL", qty=10, price=100.0)

    # Widening stocks -> both excludes no held class, so nothing is sold and the
    # broker is never touched.
    updated = service.change_session_scope(
        db_session, session_id=sess.id, scope="both", broker=_BoomBroker()
    )
    assert (updated.session_metadata or {})["asset_types"] == "both"
    assert {p.ticker for p in service.list_open_positions(db_session, sess.id)} == {
        "AAPL"
    }
    assert service.get_session(db_session, sess.id).total_fees == pytest.approx(0.0)


def test_change_session_scope_narrowing_liquidates_out_of_scope_holdings(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _set_scope(db_session, sess.id, "both")
    _asset(db_session, "AAPL", AssetCategory.STOCK)
    _asset(db_session, "BTC-USD", AssetCategory.CRYPTO)

    # Seed the broker's own positions so execute_close can sell them, mirrored into
    # the session ledger.
    broker = StubBroker(initial_cash=10_000_000.0)
    broker.buy("AAPL", 10, asset_class=AssetClass.EQUITY)
    broker.buy("BTC-USD", 1.0, asset_class=AssetClass.CRYPTO)
    _buy(db_session, sess.id, "AAPL", qty=10, price=100.0)
    _buy(db_session, sess.id, "BTC-USD", qty=1.0, price=50_000.0)

    updated = service.change_session_scope(
        db_session, session_id=sess.id, scope="stocks", broker=broker
    )

    # Scope persisted; the crypto position was sold and the equity position kept.
    assert (updated.session_metadata or {})["asset_types"] == "stocks"
    assert {p.ticker for p in service.list_open_positions(db_session, sess.id)} == {
        "AAPL"
    }
    closed = service.get_closed_positions(db_session, sess.id, limit=100)
    assert {c.ticker for c in closed} == {"BTC-USD"}

    # The forced sell was recorded as a trade tagged for the scope change. It is a
    # crypto position, so total_fees carries the percentage fee on its notional.
    row = service.get_session(db_session, sess.id)
    (sell,) = service.get_session_trades(db_session, sess.id)
    executed = sell.filled_price if sell.filled_price is not None else sell.price
    assert settings.CRYPTO_FEE_PCT > 0.0  # default model charges crypto
    assert row.total_fees == pytest.approx(
        settings.CRYPTO_FEE_PCT * sell.quantity * executed
    )
    assert row.total_trades == 1
    trades = service.get_session_trades(db_session, sess.id)
    assert [t.signal_type for t in trades] == [service.SCOPE_CHANGE_SIGNAL_TYPE]
    assert trades[0].ticker == "BTC-USD"

    # The value snapshot was refreshed (the sales are reflected in a snapshot row).
    assert service.list_value_snapshots(db_session, session_id=sess.id)


def test_value_history_attaches_rebased_benchmark_values(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    broker = _QuoteBroker({})
    start = date(2026, 1, 5)
    later = date(2026, 1, 6)
    for day in (start, later):
        service.record_value_snapshot(
            db_session, session_id=sess.id, as_of=day, broker=broker
        )
    _add_benchmark_price(db_session, "SP500", start, 200.0)
    _add_benchmark_price(db_session, "SP500", later, 220.0)

    points = service.list_value_history(db_session, session_id=sess.id)
    # First snapshot rebases to allocated capital; +10% on the second day.
    assert points[0].benchmark_value == pytest.approx(100_000.0)
    assert points[1].benchmark_value == pytest.approx(110_000.0)


def test_value_history_benchmark_value_null_without_prices(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    broker = _QuoteBroker({})
    service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=date(2026, 1, 5), broker=broker
    )
    points = service.list_value_history(db_session, session_id=sess.id)
    # No stored benchmark prices -> the overlay value is null, not an error.
    assert points[0].benchmark_value is None


def test_session_kpis_benchmark_return_and_excess(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +20/share -> +200 unrealised
    start = date(2026, 1, 5)
    service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=start, broker=_QuoteBroker({"AAPL": 100.0})
    )
    # Benchmark up 10% from the session start close to the latest close.
    _add_benchmark_price(db_session, "SP500", start, 100.0)
    _add_benchmark_price(db_session, "SP500", start + timedelta(days=30), 110.0)

    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    assert kpis.benchmark == Benchmark.SP500.value
    assert kpis.benchmark_return_pct == pytest.approx(0.10)
    assert kpis.excess_return_pct == pytest.approx(kpis.total_return_pct - 0.10)
    # Absolute excess equals the fractional excess on allocated capital.
    allocated = kpis.current_value - kpis.total_return
    assert kpis.excess_return == pytest.approx(kpis.excess_return_pct * allocated)


def test_session_kpis_benchmark_none_without_prices(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    # No stored benchmark prices -> comparison figures are withheld.
    assert kpis.benchmark == Benchmark.SP500.value
    assert kpis.benchmark_return_pct is None
    assert kpis.excess_return_pct is None
    assert kpis.excess_return is None


# --------------------------------------------------------------------------- #
# Sector / category performance attribution
# --------------------------------------------------------------------------- #


def _asset(
    db_session: Session,
    ticker: str,
    category: AssetCategory,
    sector: Sector | None = None,
) -> Asset:
    """Insert a catalogue asset with the given category/sector."""
    asset = Asset(
        ticker=ticker,
        category=category.value,
        sector=sector.value if sector is not None else None,
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.commit()
    return asset


def _close(
    db_session: Session,
    session_id: object,
    ticker: str,
    qty: float,
    entry: float,
    exit_price: float,
) -> None:
    service.record_closed_position(
        db_session,
        session_id=session_id,
        ticker=ticker,
        quantity=qty,
        entry_price=entry,
        exit_price=exit_price,
        entry_date=datetime(2026, 1, 1, tzinfo=UTC),
        exit_date=datetime(2026, 1, 10, tzinfo=UTC),
    )


def test_sector_performance_join_matches_regardless_of_casing(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _asset(db_session, "AAPL", AssetCategory.STOCK, Sector.TECHNOLOGY)
    # Ledger ticker stored lower-cased; the catalogue stores the normalised form.
    _buy(db_session, sess.id, "aapl", 10, 100.0)

    result = service.session_sector_performance(
        db_session, session_id=sess.id, broker=_QuoteBroker({"aapl": 120.0})
    )
    # The join normalises casing -> matched to the tech sector, not "Unknown".
    (sector_group,) = result.by_sector
    assert sector_group.key == Sector.TECHNOLOGY.value
    assert sector_group.unrealized_pnl == pytest.approx(200.0)
    (category_group,) = result.by_category
    assert category_group.key == AssetCategory.STOCK.value


def test_sector_performance_total_is_realised_plus_unrealised(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _asset(db_session, "AAPL", AssetCategory.STOCK, Sector.TECHNOLOGY)
    _asset(db_session, "MSFT", AssetCategory.STOCK, Sector.TECHNOLOGY)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +200 unrealised at 120
    _close(db_session, sess.id, "MSFT", 10, 100.0, 130.0)  # +300 realised

    result = service.session_sector_performance(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    (tech,) = result.by_sector
    assert tech.key == Sector.TECHNOLOGY.value
    assert tech.realized_pnl == pytest.approx(300.0)
    assert tech.unrealized_pnl == pytest.approx(200.0)
    assert tech.total_pnl == pytest.approx(500.0)
    assert tech.total_pnl == pytest.approx(tech.realized_pnl + tech.unrealized_pnl)


def test_sector_performance_null_sector_bucketed_but_category_kept(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _asset(db_session, "BTC-USD", AssetCategory.CRYPTO, sector=None)
    _buy(db_session, sess.id, "BTC-USD", 1, 1000.0)

    result = service.session_sector_performance(
        db_session, session_id=sess.id, broker=_QuoteBroker({"BTC-USD": 1200.0})
    )
    # No sector -> the dedicated bucket in the by-sector grouping ...
    (sector_group,) = result.by_sector
    assert sector_group.key == service.NO_SECTOR_GROUP_KEY
    # ... but the category is still used in the by-category grouping.
    (category_group,) = result.by_category
    assert category_group.key == AssetCategory.CRYPTO.value
    assert category_group.unrealized_pnl == pytest.approx(200.0)


def test_sector_performance_unknown_ticker_bucketed_nothing_dropped(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _asset(db_session, "AAPL", AssetCategory.STOCK, Sector.TECHNOLOGY)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +200 unrealised at 120
    # FOO / BAR have no catalogue asset -> the "Unknown" bucket.
    _buy(db_session, sess.id, "FOO", 5, 10.0)  # +10 unrealised at 12
    _close(db_session, sess.id, "BAR", 10, 100.0, 90.0)  # -100 realised

    result = service.session_sector_performance(
        db_session,
        session_id=sess.id,
        broker=_QuoteBroker({"AAPL": 120.0, "FOO": 12.0}),
    )
    sector_keys = {g.key for g in result.by_sector}
    assert service.UNKNOWN_GROUP_KEY in sector_keys
    assert service.UNKNOWN_GROUP_KEY in {g.key for g in result.by_category}
    # Overall P&L = -100 realised + (200 + 10) unrealised = 110; nothing dropped.
    expected_total = 110.0
    assert sum(g.total_pnl for g in result.by_sector) == pytest.approx(expected_total)
    assert sum(g.total_pnl for g in result.by_category) == pytest.approx(expected_total)


def test_sector_performance_zero_cost_basis_return_is_none(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    # Closed at a zero entry price -> the group's invested cost basis is zero.
    _asset(db_session, "FREE", AssetCategory.STOCK, Sector.ENERGY)
    _close(db_session, sess.id, "FREE", 10, 0.0, 5.0)  # +50 realised, 0 cost

    result = service.session_sector_performance(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    (energy,) = result.by_sector
    assert energy.key == Sector.ENERGY.value
    assert energy.total_pnl == pytest.approx(50.0)
    assert energy.return_pct is None


def test_sector_performance_unknown_session_raises(db_session: Session) -> None:
    with pytest.raises(SessionNotFoundError):
        service.session_sector_performance(
            db_session, session_id=uuid.uuid4(), broker=_QuoteBroker({})
        )


# --------------------------------------------------------------------------- #
# Capital increase: ledger + contribution set + time-weighted analytics
# --------------------------------------------------------------------------- #


def _event(effective_date: date, amount: float, order: int = 0) -> SessionCapitalEvent:
    """A transient capital event for pure-helper tests (distinct created_at)."""
    return SessionCapitalEvent(
        amount=amount,
        effective_date=effective_date,
        created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=order),
    )


def test_session_contributions_no_events_single_baseline(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)  # allocated 100k, no events
    start = date(2026, 1, 1)
    contributions = service.session_contributions(sess, [], start_date=start)
    # The whole allocated capital is a single baseline contribution on the start date.
    assert contributions == [Contribution(effective_date=start, amount=100_000.0)]


def test_session_contributions_two_events_baseline_plus_rows(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)  # allocated 100k
    sess.allocated_capital = 130_000.0  # original 100k + two increases (20k, 10k)
    start = date(2026, 1, 1)
    events = [
        _event(date(2026, 1, 10), 20_000.0, order=0),
        _event(date(2026, 1, 20), 10_000.0, order=1),
    ]
    contributions = service.session_contributions(sess, events, start_date=start)
    # Baseline = allocated − Σ events; then one row per event in effective-date order.
    assert contributions == [
        Contribution(effective_date=start, amount=100_000.0),
        Contribution(effective_date=date(2026, 1, 10), amount=20_000.0),
        Contribution(effective_date=date(2026, 1, 20), amount=10_000.0),
    ]


def test_increase_session_capital_raises_capital_records_event_and_cash(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)  # all cash, 100k
    updated = service.increase_session_capital(
        db_session, session_id=sess.id, amount=25_000.0
    )
    # Contributed capital rose by the amount and exactly one event row was written.
    assert updated.allocated_capital == pytest.approx(125_000.0)
    events = service.list_capital_events(db_session, session_id=sess.id)
    assert len(events) == 1
    assert events[0].amount == pytest.approx(25_000.0)
    assert events[0].effective_date == datetime.now(tz=UTC).date()
    # The derived cash (and thus investable value) rose by the same amount.
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    assert valuation.cash_value == pytest.approx(125_000.0)


def test_increase_session_capital_rejects_non_positive(db_session: Session) -> None:
    sess = _ai_session(db_session)
    for bad in (0.0, -100.0):
        with pytest.raises(InvalidCapitalChangeError):
            service.increase_session_capital(
                db_session, session_id=sess.id, amount=bad
            )
    # The session was left unchanged and no event was recorded.
    assert service.get_session(db_session, sess.id).allocated_capital == pytest.approx(
        100_000.0
    )
    assert service.list_capital_events(db_session, session_id=sess.id) == []


def test_increase_session_capital_unknown_session_raises(
    db_session: Session,
) -> None:
    with pytest.raises(SessionNotFoundError):
        service.increase_session_capital(
            db_session, session_id=uuid.uuid4(), amount=1_000.0
        )


def test_contribution_adjusted_returns_excludes_contribution_day(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    sess.allocated_capital = 150_000.0  # 100k baseline + 50k contributed on day 2
    start = date(2026, 1, 1)
    contributions = service.session_contributions(
        sess, [_event(date(2026, 1, 2), 50_000.0)], start_date=start
    )
    snaps = [
        SessionValueSnapshot(snapshot_date=date(2026, 1, 1), total_value=110_000.0),
        SessionValueSnapshot(snapshot_date=date(2026, 1, 2), total_value=170_000.0),
        SessionValueSnapshot(snapshot_date=date(2026, 1, 3), total_value=180_000.0),
    ]
    returns = service.contribution_adjusted_returns(snaps, contributions)
    # Day 1: (110k − 100k)/100k. Day 2 nets out the 50k deposit: (170k − 50k − 110k)/110k
    # — NOT the naive (170k − 110k)/110k = 0.545 which would count the deposit as a gain.
    assert returns == pytest.approx([0.10, 10_000.0 / 110_000.0, 10_000.0 / 170_000.0])


def test_session_kpis_contribution_not_counted_as_gain(db_session: Session) -> None:
    sess = _ai_session(db_session)
    base = date(2026, 1, 1)
    # Flat NAV at the 100k baseline for two days, then capital is doubled and NAV
    # jumps to 200k purely from the deposit (no market move).
    _add_value_snapshot(db_session, sess.id, base, 100_000.0)
    service.increase_session_capital(db_session, session_id=sess.id, amount=100_000.0)
    # Overwrite today's auto-snapshot with the post-deposit NAV for a clean series.
    today = datetime.now(tz=UTC).date()
    service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=today, broker=_QuoteBroker({})
    )
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    # The pure cash injection is not a gain: time-weighted return stays ~0 even though
    # the absolute value doubled. (Absolute total_return is value − contributed = 0.)
    assert kpis.total_return_pct == pytest.approx(0.0, abs=1e-9)
    assert kpis.total_return == pytest.approx(0.0)
    assert kpis.current_value == pytest.approx(200_000.0)


def test_session_kpis_without_contribution_matches_simple_return(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +20/share live
    base = date(2026, 1, 1)
    for value in (100_000.0, 101_000.0):
        _add_value_snapshot(db_session, sess.id, base, value)
        base += timedelta(days=1)
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    # With no contributions the time-weighted return equals the simple return against
    # allocated capital: (current_value − allocated)/allocated.
    assert kpis.total_return_pct == pytest.approx(kpis.total_return / 100_000.0)


def test_record_value_snapshot_excludes_same_day_contribution(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    today = datetime.now(tz=UTC).date()
    # Add capital today, then snapshot the same day.
    service.increase_session_capital(db_session, session_id=sess.id, amount=40_000.0)
    snap = service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=today, broker=_QuoteBroker({})
    )
    # Value is 140k but the 40k added today is not reported as a gain.
    assert snap.total_value == pytest.approx(140_000.0)
    assert snap.daily_pnl == pytest.approx(0.0)
    assert snap.daily_pnl_pct == pytest.approx(0.0)


def test_value_history_steps_up_on_later_contribution(db_session: Session) -> None:
    sess = _ai_session(db_session)
    broker = _QuoteBroker({})
    start = date(2026, 1, 5)
    later = date(2026, 1, 6)
    service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=start, broker=broker
    )
    # Record a second-day snapshot and a capital event effective that day.
    service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=later, broker=broker
    )
    db_session.add(
        SessionCapitalEvent(
            session_id=sess.id, amount=50_000.0, effective_date=later
        )
    )
    sess.allocated_capital = 150_000.0
    db_session.commit()
    _add_benchmark_price(db_session, "SP500", start, 200.0)
    _add_benchmark_price(db_session, "SP500", later, 220.0)

    points = service.list_value_history(db_session, session_id=sess.id)
    # Day 1: only the 100k baseline is in effect -> rebased to 100k.
    assert points[0].benchmark_value == pytest.approx(100_000.0)
    # Day 2: baseline grew +10% (110k) and the fresh 50k is added at that day's close.
    assert points[1].benchmark_value == pytest.approx(110_000.0 + 50_000.0)
