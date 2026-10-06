"""Tests for :class:`AIPortfolioExecutor` driving orders through a stub broker."""

from __future__ import annotations

import pytest

from cadence.ai_portfolio.agent import AIPortfolioStock, AITargetAllocation
from cadence.ai_portfolio.executor import (
    AIPortfolioExecutor,
    GuardrailCaps,
    _OrderIntent,
    enforce_guardrails,
)
from cadence.broker.base import OrderError
from cadence.broker.models import (
    AssetClass,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    TimeInForce,
)
from cadence.broker.stub import StubBroker
from cadence.config import settings


@pytest.fixture(autouse=True)
def _no_cash_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the cash-buffer reserve off so sizing tests assert the raw base.

    The executor now reserves ``max(base * REBALANCE_CASH_BUFFER_PCT,
    candidate_count * TRANSACTION_COST_USD)`` before sizing. The bulk of this
    suite asserts base-scaling / delta semantics, so we disable the reserve by
    default; the dedicated cash-buffer tests re-enable it with their own
    ``monkeypatch.setattr`` calls, which take effect after this fixture.
    """
    monkeypatch.setattr(settings, "REBALANCE_CASH_BUFFER_PCT", 0.0)
    monkeypatch.setattr(settings, "TRANSACTION_COST_USD", 0.0)


def _stock(ticker: str, alloc: float) -> AIPortfolioStock:
    return AIPortfolioStock(
        ticker=ticker,
        company_name=ticker,
        allocation_pct=alloc,
        investment_thesis="thesis",
        confidence=0.7,
    )


def _target(ticker: str, alloc: float) -> AITargetAllocation:
    return AITargetAllocation(
        ticker=ticker,
        company_name=ticker,
        allocation_pct=alloc,
        investment_thesis="thesis",
        confidence=0.7,
    )


class _FailingBroker(StubBroker):
    """StubBroker that raises on buying a specific ticker (to test isolation)."""

    def __init__(self, fail_ticker: str) -> None:
        super().__init__()
        self._fail_ticker = fail_ticker

    def buy(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        asset_class: AssetClass = AssetClass.EQUITY,
    ):  # type: ignore[override]
        if symbol == self._fail_ticker:
            raise OrderError(f"forced failure for {symbol}")
        return super().buy(
            symbol, quantity, order_type, limit_price, time_in_force, asset_class
        )


# --------------------------------------------------------------------------- #
# Build sizing (long-only)
# --------------------------------------------------------------------------- #


def test_execute_build_sizes_positions_from_capital() -> None:
    broker = StubBroker()
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_build([_stock("AAPL", 0.5), _stock("MSFT", 0.5)])

    assert len(results) == 2
    assert all(r.executed for r in results)
    for r in results:
        assert r.side == "long"
        assert r.shares >= 1
        assert r.order_id is not None


def test_execute_build_skips_sub_one_share_positions() -> None:
    broker = StubBroker()
    # Tiny capital: each 0.5 allocation buys < 1 share at any stub price.
    executor = AIPortfolioExecutor(broker, allocated_capital=10)

    results = executor.execute_build([_stock("AAPL", 0.5), _stock("MSFT", 0.5)])

    assert all(not r.executed for r in results)
    assert all(r.shares == 0 for r in results)


def test_execute_build_isolates_per_ticker_failures() -> None:
    broker = _FailingBroker(fail_ticker="AAPL")
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_build([_stock("AAPL", 0.5), _stock("MSFT", 0.5)])

    by_ticker = {r.ticker: r for r in results}
    assert by_ticker["AAPL"].executed is False
    assert "failed" in by_ticker["AAPL"].reason.lower()
    # The other ticker still executes.
    assert by_ticker["MSFT"].executed is True


# --------------------------------------------------------------------------- #
# Target-weight rebalance
# --------------------------------------------------------------------------- #


def test_execute_rebalance_trades_toward_target_weights() -> None:
    broker = StubBroker()
    # Establish held long positions: one to increase, one to decrease, one to exit.
    broker.buy("AAPL", 10)
    broker.buy("MSFT", 20)
    broker.buy("GOOG", 5)
    positions = {p.symbol: p for p in broker.get_positions()}

    executor = AIPortfolioExecutor(broker, allocated_capital=50_000)
    results = executor.execute_rebalance(
        targets=[
            _target("AAPL", 0.5),  # increase (target shares > 10)
            _target("MSFT", 0.05),  # decrease (target shares < 20)
            _target("NVDA", 0.45),  # brand-new long
            # GOOG omitted -> full exit
        ],
        current_positions=positions,
    )

    by_ticker = {r.ticker: r for r in results}

    # Increase is a buy.
    assert by_ticker["AAPL"].executed is True
    assert by_ticker["AAPL"].side == "long"
    assert by_ticker["AAPL"].shares >= 1

    # Decrease is a sell of the delta (< held quantity).
    assert by_ticker["MSFT"].executed is True
    assert by_ticker["MSFT"].side == "sell"
    assert 0 < by_ticker["MSFT"].shares < 20

    # Held-but-untargeted ticker is fully sold.
    assert by_ticker["GOOG"].executed is True
    assert by_ticker["GOOG"].side == "sell"
    assert by_ticker["GOOG"].shares == 5

    # A new target opens a long position.
    assert by_ticker["NVDA"].executed is True
    assert by_ticker["NVDA"].side == "long"
    assert by_ticker["NVDA"].shares >= 1


def test_execute_rebalance_base_capital_scales_targets() -> None:
    # Same target weights + no current positions: a larger rebalance base_capital
    # buys strictly more shares. Omitting base_capital falls back to the executor's
    # allocated_capital (the build-time base), leaving build behaviour unchanged.
    broker = StubBroker()
    price = broker.get_quote("AAPL").last
    executor = AIPortfolioExecutor(broker, allocated_capital=100 * price)

    small = executor.execute_rebalance(
        targets=[_target("AAPL", 1.0)],
        current_positions={},
        base_capital=100 * price,
    )
    large = executor.execute_rebalance(
        targets=[_target("AAPL", 1.0)],
        current_positions={p.symbol: p for p in broker.get_positions()},
        base_capital=250 * price,
    )
    # First run bought ~100 shares toward the 100-share target; the second run,
    # sized against a larger base, buys the delta up to ~250 shares.
    assert small[0].side == "long"
    assert small[0].shares == pytest.approx(100, abs=1)
    assert large[0].side == "long"
    assert large[0].shares == pytest.approx(150, abs=1)

    # Falling back to allocated_capital (no base_capital) reproduces the build base.
    fresh = StubBroker()
    fresh_exec = AIPortfolioExecutor(fresh, allocated_capital=100 * price)
    fallback = fresh_exec.execute_rebalance(
        targets=[_target("AAPL", 1.0)],
        current_positions={},
    )
    assert fallback[0].shares == pytest.approx(100, abs=1)


def test_execute_rebalance_skips_trivial_deltas() -> None:
    broker = StubBroker()
    broker.buy("AAPL", 10)
    positions = {p.symbol: p for p in broker.get_positions()}
    price = broker.get_quote("AAPL").last

    # With a single target the weight normalizes to 1.0, so size the capital so
    # the target share count rounds to exactly the 10 held shares -> delta 0.
    executor = AIPortfolioExecutor(broker, allocated_capital=price * 10.4)
    results = executor.execute_rebalance(
        targets=[_target("AAPL", 1.0)],
        current_positions=positions,
    )

    assert results == []


def test_execute_rebalance_zero_total_weight_exits_all() -> None:
    broker = StubBroker()
    broker.buy("AAPL", 3)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    # Guard against a zero-sum target set: every held position is exited.
    results = executor.execute_rebalance(targets=[], current_positions=positions)

    assert len(results) == 1
    assert results[0].ticker == "AAPL"
    assert results[0].side == "sell"
    assert results[0].shares == 3


# --------------------------------------------------------------------------- #
# Crypto: fractional, class-aware sizing
# --------------------------------------------------------------------------- #

_CRYPTO = {"BTC-USD": AssetClass.CRYPTO}


def test_execute_build_crypto_places_fractional_units() -> None:
    broker = StubBroker()
    price = broker.get_quote("BTC-USD").last
    # A single crypto pick normalizes to weight 1.0; allocate 0.25 units' worth.
    executor = AIPortfolioExecutor(broker, allocated_capital=price * 0.25)

    results = executor.execute_build(
        [_stock("BTC-USD", 1.0)], asset_classes=_CRYPTO
    )

    assert len(results) == 1
    assert results[0].executed is True
    assert 0 < results[0].shares < 1  # fractional unit placed, not skipped


def test_execute_build_crypto_skips_below_min_notional() -> None:
    broker = StubBroker()
    # $0.50 allocation is below the ~$1 crypto minimum notional -> skipped.
    executor = AIPortfolioExecutor(broker, allocated_capital=0.5)

    results = executor.execute_build(
        [_stock("BTC-USD", 1.0)], asset_classes=_CRYPTO
    )

    assert results[0].executed is False
    assert results[0].shares == 0
    assert "notional" in results[0].reason.lower()


def test_execute_rebalance_crypto_buys_fractional_delta() -> None:
    broker = StubBroker()
    broker.buy("BTC-USD", 1.0)
    positions = {p.symbol: p for p in broker.get_positions()}
    price = broker.get_quote("BTC-USD").last
    # Target 2 units vs 1 held -> buy 1.0 fractional-capable unit.
    executor = AIPortfolioExecutor(broker, allocated_capital=price * 2)

    results = executor.execute_rebalance(
        targets=[_target("BTC-USD", 1.0)],
        current_positions=positions,
        asset_classes=_CRYPTO,
    )

    assert len(results) == 1
    assert results[0].side == "long"
    assert results[0].shares == pytest.approx(1.0)


def test_execute_rebalance_crypto_exit_sells_full_float_qty() -> None:
    broker = StubBroker()
    broker.buy("BTC-USD", 0.5)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        targets=[],  # crypto omitted -> full exit
        current_positions=positions,
        asset_classes=_CRYPTO,
    )

    assert len(results) == 1
    assert results[0].side == "sell"
    assert results[0].shares == pytest.approx(0.5)
    assert "exit" in results[0].reason.lower()


def test_execute_rebalance_market_closed_skips_equity_trades_crypto() -> None:
    broker = StubBroker()
    broker.buy("AAPL", 10)
    broker.buy("BTC-USD", 1.0)
    positions = {p.symbol: p for p in broker.get_positions()}
    price_btc = broker.get_quote("BTC-USD").last
    executor = AIPortfolioExecutor(broker, allocated_capital=price_btc * 4)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 0.5), _target("BTC-USD", 0.5)],
        current_positions=positions,
        asset_classes=_CRYPTO,
        market_open=False,
    )

    by_ticker = {r.ticker: r for r in results}
    # Equity is not traded while the market is closed.
    assert by_ticker["AAPL"].executed is False
    assert by_ticker["AAPL"].reason == "equity market closed"
    # Crypto still trades.
    assert by_ticker["BTC-USD"].executed is True
    assert by_ticker["BTC-USD"].side == "long"


_MIXED = {"AAPL": AssetClass.EQUITY, "BTC-USD": AssetClass.CRYPTO}


def test_execute_rebalance_crypto_only_sizes_off_budget_leaves_equity() -> None:
    # The weekend crypto-only run: crypto is sized off the passed crypto budget
    # (NOT allocated_capital), and the held equity is never touched or sold even
    # though the AI returned a target for it.
    broker = StubBroker()
    broker.buy("AAPL", 10)
    positions = {p.symbol: p for p in broker.get_positions()}
    aapl_qty_before = positions["AAPL"].quantity
    price_btc = broker.get_quote("BTC-USD").last
    crypto_budget = price_btc * 3
    # allocated_capital is deliberately far from the budget so a budget-sized buy
    # is distinguishable from an allocated-capital-sized one.
    executor = AIPortfolioExecutor(broker, allocated_capital=1_000_000.0)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 0.5), _target("BTC-USD", 0.5)],
        current_positions=positions,
        asset_classes=_MIXED,
        base_capital=crypto_budget,
        crypto_only=True,
    )

    # Only crypto was traded; the equity produced no order at all (not even a sell).
    assert [r.ticker for r in results] == ["BTC-USD"]
    btc = results[0]
    assert btc.side == "long"
    # Crypto weight normalizes to 1.0 among crypto-only targets and sizes off the
    # budget: 3 units' worth, not 1_000_000 / price.
    assert btc.shares == pytest.approx(3.0)
    # The held equity is untouched in the broker.
    aapl_after = {p.symbol: p for p in broker.get_positions()}["AAPL"]
    assert aapl_after.quantity == aapl_qty_before


# --------------------------------------------------------------------------- #
# Close: full liquidation regardless of market hours
# --------------------------------------------------------------------------- #


class _MarketClosedBroker(StubBroker):
    """StubBroker reporting the market as closed (close must ignore this)."""

    def is_market_open(self) -> bool:  # type: ignore[override]
        return False


class _FailingSellBroker(StubBroker):
    """StubBroker that raises when selling a specific ticker (isolation test)."""

    def __init__(self, fail_ticker: str) -> None:
        super().__init__()
        self._fail_ticker = fail_ticker

    def sell(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        asset_class: AssetClass = AssetClass.EQUITY,
    ):  # type: ignore[override]
        if symbol == self._fail_ticker:
            raise OrderError(f"forced sell failure for {symbol}")
        return super().sell(
            symbol, quantity, order_type, limit_price, time_in_force, asset_class
        )


def test_execute_close_liquidates_every_position_in_full() -> None:
    broker = StubBroker()
    broker.buy("AAPL", 10)
    broker.buy("BTC-USD", 0.5, asset_class=AssetClass.CRYPTO)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_close(positions, asset_classes=_CRYPTO)

    by_ticker = {r.ticker: r for r in results}
    assert by_ticker["AAPL"].side == "sell"
    assert by_ticker["AAPL"].shares == 10
    assert by_ticker["AAPL"].executed is True
    assert by_ticker["BTC-USD"].side == "sell"
    assert by_ticker["BTC-USD"].shares == pytest.approx(0.5)
    assert by_ticker["BTC-USD"].executed is True
    # Nothing is left held after a full liquidation.
    assert broker.get_positions() == []


def test_execute_close_sells_equities_even_when_market_closed() -> None:
    broker = _MarketClosedBroker()
    broker.buy("AAPL", 4)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_close(positions)

    assert len(results) == 1
    assert results[0].ticker == "AAPL"
    assert results[0].executed is True
    assert results[0].shares == 4


def test_execute_close_isolates_per_ticker_failures() -> None:
    broker = _FailingSellBroker("MSFT")
    broker.buy("AAPL", 5)
    broker.buy("MSFT", 7)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_close(positions)

    by_ticker = {r.ticker: r for r in results}
    assert by_ticker["AAPL"].executed is True
    assert by_ticker["MSFT"].executed is False
    assert "failed" in by_ticker["MSFT"].reason.lower()


def test_position_helper_import_available() -> None:
    # Sanity: the Position model used to size positions is importable.
    assert Position(symbol="X", quantity=0.0, avg_cost=0.0).symbol == "X"


# --------------------------------------------------------------------------- #
# Deterministic risk guardrails (enforce_guardrails + executor seams)
# --------------------------------------------------------------------------- #


def _classes(**kw: AssetClass) -> dict[str, AssetClass]:
    return dict(kw)


def _no_class_caps(max_per_asset: float, max_invested: float = 1.0) -> GuardrailCaps:
    return GuardrailCaps(
        max_per_asset=max_per_asset, max_per_class=1.0, max_invested=max_invested
    )


def test_enforce_guardrails_no_caps_is_normalization_only() -> None:
    w = enforce_guardrails(
        {"A": 2.0, "B": 2.0},
        _classes(A=AssetClass.EQUITY, B=AssetClass.EQUITY),
        GuardrailCaps(max_per_asset=1.0, max_per_class=1.0, max_invested=1.0),
    )
    assert w == pytest.approx({"A": 0.5, "B": 0.5})


def test_enforce_guardrails_clamps_and_redistributes_per_asset() -> None:
    # A wants 80%, cap 40% -> A pinned to 40%, excess flows to B and C.
    w = enforce_guardrails(
        {"A": 0.8, "B": 0.1, "C": 0.1},
        _classes(A=AssetClass.EQUITY, B=AssetClass.EQUITY, C=AssetClass.EQUITY),
        _no_class_caps(0.4),
    )
    assert w["A"] == pytest.approx(0.4)
    assert w["B"] == pytest.approx(0.3)
    assert w["C"] == pytest.approx(0.3)
    assert sum(w.values()) == pytest.approx(1.0)


def test_enforce_guardrails_caps_asset_class() -> None:
    # Two crypto names sum to 100% raw; per-class cap 50% shifts half to the equity.
    w = enforce_guardrails(
        {"BTC": 0.5, "ETH": 0.5, "AAA": 0.0001},
        _classes(BTC=AssetClass.CRYPTO, ETH=AssetClass.CRYPTO, AAA=AssetClass.EQUITY),
        GuardrailCaps(max_per_asset=1.0, max_per_class=0.5, max_invested=1.0),
    )
    crypto = w["BTC"] + w["ETH"]
    assert crypto == pytest.approx(0.5, abs=1e-6)
    assert w["AAA"] == pytest.approx(0.5, abs=1e-6)
    assert sum(w.values()) == pytest.approx(1.0)


def test_enforce_guardrails_holds_cash_buffer() -> None:
    w = enforce_guardrails(
        {"A": 0.5, "B": 0.5},
        _classes(A=AssetClass.EQUITY, B=AssetClass.EQUITY),
        GuardrailCaps(max_per_asset=1.0, max_per_class=1.0, max_invested=0.9),
    )
    assert sum(w.values()) == pytest.approx(0.9)
    assert w["A"] == pytest.approx(0.45)
    assert w["B"] == pytest.approx(0.45)


def test_enforce_guardrails_infeasible_caps_leave_cash() -> None:
    # 2 assets, 30% cap each -> at most 60% investable; the rest stays as cash.
    w = enforce_guardrails(
        {"A": 0.5, "B": 0.5},
        _classes(A=AssetClass.EQUITY, B=AssetClass.EQUITY),
        _no_class_caps(0.3),
    )
    assert w["A"] == pytest.approx(0.3)
    assert w["B"] == pytest.approx(0.3)
    assert sum(w.values()) == pytest.approx(0.6)


def test_enforce_guardrails_respects_both_caps_at_fixed_point() -> None:
    # Adversarial: per-asset 0.5, per-class 0.5, three names two of which share a class.
    classes = _classes(
        BTC=AssetClass.CRYPTO, ETH=AssetClass.CRYPTO, AAA=AssetClass.EQUITY
    )
    w = enforce_guardrails(
        {"BTC": 0.6, "ETH": 0.3, "AAA": 0.1},
        classes,
        GuardrailCaps(max_per_asset=0.5, max_per_class=0.5, max_invested=1.0),
    )
    assert all(v <= 0.5 + 1e-9 for v in w.values())
    assert (w["BTC"] + w["ETH"]) <= 0.5 + 1e-9
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-6)


def test_enforce_guardrails_empty_when_no_positive_weights() -> None:
    assert enforce_guardrails({"A": 0.0}, _classes(A=AssetClass.EQUITY),
                              _no_class_caps(0.5)) == {"A": 0.0}


def test_execute_build_with_caps_bounds_per_asset_notional() -> None:
    # AAA wants 90%; a 40% per-asset cap bounds its notional to 40% of capital.
    broker = StubBroker()
    price = broker.get_quote("AAA", AssetClass.EQUITY).last
    ex = AIPortfolioExecutor(broker, allocated_capital=10_000)
    results = ex.execute_build(
        [_stock("AAA", 0.9), _stock("BBB", 0.05), _stock("CCC", 0.05)],
        asset_classes={
            "AAA": AssetClass.EQUITY,
            "BBB": AssetClass.EQUITY,
            "CCC": AssetClass.EQUITY,
        },
        caps=_no_class_caps(0.4),
    )
    by = {r.ticker: r for r in results}
    assert by["AAA"].shares == pytest.approx(int(0.4 * 10_000 / price))
    assert by["AAA"].executed


def test_execute_rebalance_with_caps_bounds_target_shares() -> None:
    broker = StubBroker()
    price = broker.get_quote("AAA", AssetClass.EQUITY).last
    ex = AIPortfolioExecutor(broker, allocated_capital=10_000)
    results = ex.execute_rebalance(
        [_target("AAA", 0.9), _target("BBB", 0.1)],
        current_positions={},
        asset_classes={"AAA": AssetClass.EQUITY, "BBB": AssetClass.EQUITY},
        caps=_no_class_caps(0.4),
    )
    by = {r.ticker: r for r in results}
    assert by["AAA"].shares == pytest.approx(int(0.4 * 10_000 / price))


def test_execute_build_without_caps_unchanged() -> None:
    # No caps: AAA keeps its full 90% weight (36 shares of ~$245 from $10k).
    broker = StubBroker()
    price = broker.get_quote("AAA", AssetClass.EQUITY).last
    ex = AIPortfolioExecutor(broker, allocated_capital=10_000)
    results = ex.execute_build(
        [_stock("AAA", 0.9), _stock("BBB", 0.1)],
        asset_classes={"AAA": AssetClass.EQUITY, "BBB": AssetClass.EQUITY},
    )
    by = {r.ticker: r for r in results}
    assert by["AAA"].shares == pytest.approx(int(0.9 * 10_000 / price))


# --------------------------------------------------------------------------- #
# Sells-before-buys ordering, fill gate, timeout, and retry
# --------------------------------------------------------------------------- #


class _RecordingBroker(StubBroker):
    """StubBroker (synchronous fills) that records order-submission order."""

    def __init__(self, initial_cash: float = 1_000_000.0) -> None:
        super().__init__(initial_cash=initial_cash)
        self.calls: list[tuple[str, str]] = []

    def buy(self, symbol, quantity, order_type=OrderType.MARKET, limit_price=None,
            time_in_force=TimeInForce.DAY, asset_class=AssetClass.EQUITY):  # type: ignore[override]
        self.calls.append(("buy", symbol))
        return super().buy(symbol, quantity, order_type, limit_price,
                           time_in_force, asset_class)

    def sell(self, symbol, quantity, order_type=OrderType.MARKET, limit_price=None,
             time_in_force=TimeInForce.DAY, asset_class=AssetClass.EQUITY):  # type: ignore[override]
        self.calls.append(("sell", symbol))
        return super().sell(symbol, quantity, order_type, limit_price,
                            time_in_force, asset_class)


class _AsyncBroker(StubBroker):
    """Async broker: sells return SUBMITTED and settle after ``polls_to_settle``
    ``get_order`` polls (never, when ``settle`` is False). Buys fill immediately
    and flag if any was submitted while a sell was still non-terminal."""

    def __init__(self, *, polls_to_settle: int = 1, settle: bool = True) -> None:
        super().__init__()
        self._polls_to_settle = polls_to_settle
        self._settle = settle
        self._poll_counts: dict[str, int] = {}
        self.sell_orders: dict[str, Order] = {}
        self.buy_orders: dict[str, Order] = {}
        self.buy_submitted_while_pending = False

    def sell(self, symbol, quantity, order_type=OrderType.MARKET, limit_price=None,
             time_in_force=TimeInForce.DAY, asset_class=AssetClass.EQUITY):  # type: ignore[override]
        oid = self._next_order_id()
        order = Order(symbol=symbol, side=OrderSide.SELL, quantity=quantity,
                      asset_class=asset_class, order_id=oid,
                      status=OrderStatus.SUBMITTED, filled_price=None)
        self.sell_orders[oid] = order
        self._orders[oid] = order
        return order

    def buy(self, symbol, quantity, order_type=OrderType.MARKET, limit_price=None,
            time_in_force=TimeInForce.DAY, asset_class=AssetClass.EQUITY):  # type: ignore[override]
        if any(not o.is_complete for o in self.sell_orders.values()):
            self.buy_submitted_while_pending = True
        oid = self._next_order_id()
        order = Order(symbol=symbol, side=OrderSide.BUY, quantity=quantity,
                      asset_class=asset_class, order_id=oid,
                      status=OrderStatus.FILLED, filled_price=100.0)
        self.buy_orders[oid] = order
        self._orders[oid] = order
        return order

    def get_order(self, order_id):  # type: ignore[override]
        order = self._orders.get(order_id)
        if order is not None and order_id in self.sell_orders and \
                order.status == OrderStatus.SUBMITTED:
            self._poll_counts[order_id] = self._poll_counts.get(order_id, 0) + 1
            if self._settle and self._poll_counts[order_id] >= self._polls_to_settle:
                order.status = OrderStatus.FILLED
                order.filled_price = 50.0
        return order


class _RejectingBuyBroker(StubBroker):
    """StubBroker that returns REJECTED for the first ``reject_times`` buys of a
    given symbol, then fills; counts total buy attempts for that symbol."""

    def __init__(self, *, symbol: str, reject_times: int) -> None:
        super().__init__()
        self._symbol = symbol
        self._reject_remaining = reject_times
        self.attempts = 0

    def buy(self, symbol, quantity, order_type=OrderType.MARKET, limit_price=None,
            time_in_force=TimeInForce.DAY, asset_class=AssetClass.EQUITY):  # type: ignore[override]
        if symbol == self._symbol:
            self.attempts += 1
            if self._reject_remaining > 0:
                self._reject_remaining -= 1
                oid = self._next_order_id()
                order = Order(symbol=symbol, side=OrderSide.BUY, quantity=quantity,
                              asset_class=asset_class, order_id=oid,
                              status=OrderStatus.REJECTED, filled_price=None)
                self._orders[oid] = order
                return order
        return super().buy(symbol, quantity, order_type, limit_price,
                           time_in_force, asset_class)


# --- 2.1 / 2.2: plan/submit split ------------------------------------------ #


def test_plan_equity_sizes_delta_without_submitting() -> None:
    broker = _RecordingBroker()
    price = broker.get_quote("AAPL").last
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)
    pos = Position(symbol="AAPL", quantity=10, avg_cost=price)

    # Target 30 shares' worth vs 10 held -> buy 20.
    intent = executor._plan_equity("AAPL", pos, weight=1.0, price=price,
                                   base_capital=30 * price)
    assert intent is not None
    assert intent.side == "long"
    assert intent.quantity == 20
    # Planning submits nothing.
    assert broker.calls == []


def test_plan_crypto_sizes_fractional_delta_without_submitting() -> None:
    broker = _RecordingBroker()
    price = broker.get_quote("BTC-USD", AssetClass.CRYPTO).last
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    intent = executor._plan_crypto("BTC-USD", None, weight=1.0, price=price,
                                   base_capital=2 * price)
    assert intent is not None
    assert intent.side == "long"
    assert intent.quantity == pytest.approx(2.0)
    assert broker.calls == []


def test_submit_intent_builds_trade_result_with_order_fields() -> None:
    broker = StubBroker()
    price = broker.get_quote("AAPL").last
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)
    intent = _OrderIntent("AAPL", AssetClass.EQUITY, "long", 3, price, "Bought 3")

    result = executor._submit_intent(intent)

    assert result.executed is True
    assert result.ticker == "AAPL"
    assert result.shares == 3
    assert result.order_id is not None
    assert result.order_status == OrderStatus.FILLED
    assert result.filled_price is not None


# --- 3.1: sells before any buy --------------------------------------------- #


def test_rebalance_submits_all_sells_before_any_buy() -> None:
    broker = _RecordingBroker()
    broker.buy("AAA", 20)  # held, will be reduced/exited -> sell
    broker.buy("BBB", 20)  # held, will be exited -> sell
    broker.calls.clear()  # ignore setup buys
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    # Drop AAA/BBB (sells) and open YYY/ZZZ (buys).
    results = executor.execute_rebalance(
        targets=[_target("YYY", 0.5), _target("ZZZ", 0.5)],
        current_positions=positions,
    )

    sides = [side for side, _ in broker.calls]
    assert "sell" in sides and "buy" in sides
    last_sell = max(i for i, (s, _) in enumerate(broker.calls) if s == "sell")
    first_buy = min(i for i, (s, _) in enumerate(broker.calls) if s == "buy")
    assert last_sell < first_buy
    assert all(r.executed for r in results)


# --- 3.2 / 3.3: fill gate opens; stub completes in one run ----------------- #


def test_rebalance_withholds_buys_until_sells_settle(monkeypatch) -> None:
    monkeypatch.setattr(settings, "REBALANCE_SELL_FILL_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(settings, "REBALANCE_SELL_FILL_POLL_SECONDS", 0.0)
    broker = _AsyncBroker(polls_to_settle=2, settle=True)
    broker._positions["AAA"] = Position(symbol="AAA", quantity=20,
                                        avg_cost=10.0)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        targets=[_target("YYY", 1.0)],  # AAA dropped -> sell; YYY -> buy
        current_positions=positions,
    )

    by = {r.ticker: r for r in results}
    assert by["AAA"].side == "sell" and by["AAA"].executed is True
    assert by["YYY"].side == "long" and by["YYY"].executed is True
    # The buy was only submitted after the sell reached a terminal state.
    assert broker.buy_submitted_while_pending is False


def test_rebalance_stub_settles_sells_and_buys_in_one_run() -> None:
    # Limited cash: holding AAA consumes all cash, so a buy attempted first would
    # fail for insufficient funds. Sells-first frees the cash and the buy settles
    # within the same synchronous run.
    broker = _RecordingBroker()
    price_aaa = broker.get_quote("AAA").last
    budget = price_aaa * 15  # all cash goes into the holding to be exited
    broker = _RecordingBroker(initial_cash=budget)
    broker.buy("AAA", 15)  # cash -> ~0
    broker.calls.clear()
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        targets=[_target("YYY", 1.0)],  # exit AAA, open YYY with the freed cash
        current_positions=positions,
        base_capital=budget,  # size the buy to fit within the freed cash
    )

    by = {r.ticker: r for r in results}
    assert by["AAA"].side == "sell" and by["AAA"].executed is True
    assert by["YYY"].side == "long" and by["YYY"].executed is True


# --- 3.4: fill-wait timeout withholds buys --------------------------------- #


def test_rebalance_timeout_withholds_buys_keeps_sells(monkeypatch) -> None:
    monkeypatch.setattr(settings, "REBALANCE_SELL_FILL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(settings, "REBALANCE_SELL_FILL_POLL_SECONDS", 0.01)
    broker = _AsyncBroker(settle=False)  # sells never settle
    broker._positions["AAA"] = Position(symbol="AAA", quantity=20,
                                        avg_cost=10.0)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        targets=[_target("YYY", 1.0)],
        current_positions=positions,
    )

    by = {r.ticker: r for r in results}
    # Sell was submitted and stays executed.
    assert by["AAA"].side == "sell" and by["AAA"].executed is True
    # Buy is withheld (fail-safe) and never submitted.
    assert by["YYY"].executed is False
    assert "sells not yet filled" in by["YYY"].reason
    assert broker.buy_orders == {}


# --- 3.5: bounded retry of rejected orders --------------------------------- #


def test_rebalance_retries_rejected_order_then_fills(monkeypatch) -> None:
    monkeypatch.setattr(settings, "REBALANCE_ORDER_MAX_ATTEMPTS", 3)
    broker = _RejectingBuyBroker(symbol="YYY", reject_times=2)  # rejects 2, fills 3rd
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        targets=[_target("YYY", 1.0)],
        current_positions={},
    )

    assert broker.attempts == 3
    assert results[0].ticker == "YYY"
    assert results[0].executed is True


def test_rebalance_rejected_order_gives_up_after_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "REBALANCE_ORDER_MAX_ATTEMPTS", 3)
    broker = _RejectingBuyBroker(symbol="YYY", reject_times=99)  # always rejects
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        targets=[_target("YYY", 1.0)],
        current_positions={},
    )

    assert broker.attempts == 3
    assert results[0].ticker == "YYY"
    assert results[0].executed is False
    assert results[0].order_status == OrderStatus.REJECTED


# --------------------------------------------------------------------------- #
# Buy-only / no-deployable-cash skip (no-op rebalance)
# --------------------------------------------------------------------------- #


def test_rebalance_buy_only_no_deployable_cash_skips() -> None:
    # A buy-only plan (new target, no sells) with no free cash submits nothing and
    # flags the run as a no-op. With the buffer pinned off, reserve is 0, so
    # unallocated_cash == 0 means deployable cash is 0 -> skip.
    broker = StubBroker()
    price = broker.get_quote("AAPL").last
    executor = AIPortfolioExecutor(broker, allocated_capital=100 * price)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 1.0)],
        current_positions={},
        base_capital=100 * price,
        unallocated_cash=0.0,
    )

    assert executor.skipped_noop is True
    assert results == []
    assert broker.get_positions() == []


def test_rebalance_buy_only_with_deployable_cash_runs() -> None:
    # The same buy-only plan runs when there is free cash to fund the buys.
    broker = StubBroker()
    price = broker.get_quote("AAPL").last
    executor = AIPortfolioExecutor(broker, allocated_capital=100 * price)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 1.0)],
        current_positions={},
        base_capital=100 * price,
        unallocated_cash=100 * price,
    )

    assert executor.skipped_noop is False
    assert results[0].side == "long"
    assert results[0].executed is True
    assert results[0].shares == pytest.approx(100, abs=1)


def test_rebalance_with_sell_runs_regardless_of_cash() -> None:
    # A plan containing at least one sell reallocates even with zero free cash.
    broker = StubBroker()
    broker.buy("AAPL", 5)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        targets=[],  # full exit -> a sell
        current_positions=positions,
        unallocated_cash=0.0,
    )

    assert executor.skipped_noop is False
    assert results[0].side == "sell"
    assert results[0].executed is True
    assert results[0].shares == 5


def test_rebalance_unallocated_cash_none_preserves_behavior() -> None:
    # Omitting unallocated_cash disables the skip check: a buy-only plan runs as
    # before, preserving behaviour for callers that do not supply live cash.
    broker = StubBroker()
    price = broker.get_quote("AAPL").last
    executor = AIPortfolioExecutor(broker, allocated_capital=100 * price)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 1.0)],
        current_positions={},
        base_capital=100 * price,
    )

    assert executor.skipped_noop is False
    assert results[0].side == "long"
    assert results[0].executed is True


# --------------------------------------------------------------------------- #
# Cash-buffer reserve (keeps unallocated cash non-negative)
# --------------------------------------------------------------------------- #


def _enable_buffer(
    monkeypatch: pytest.MonkeyPatch, *, pct: float, cost: float
) -> None:
    """Re-enable the cash buffer (the module autouse fixture pins it off)."""
    monkeypatch.setattr(settings, "REBALANCE_CASH_BUFFER_PCT", pct)
    monkeypatch.setattr(settings, "TRANSACTION_COST_USD", cost)


def _deployed(results: list) -> float:
    """Total long notional actually bought across trade results."""
    return sum(r.shares * r.price for r in results if r.side == "long" and r.executed)


def test_reserve_cash_buffer_takes_greater_of_pct_and_fees(monkeypatch) -> None:
    executor = AIPortfolioExecutor(StubBroker(), allocated_capital=0.0)
    _enable_buffer(monkeypatch, pct=0.015, cost=1.0)

    # Percentage dominates: 1.5% of 100_000 = 1_500 > 2 trades * $1.
    assert executor._reserve_cash_buffer(100_000.0, 2) == pytest.approx(98_500.0)
    # Fee estimate dominates: 50 trades * $1 = 50 > 1.5% of 100 = 1.5.
    assert executor._reserve_cash_buffer(100.0, 50) == pytest.approx(50.0)


def test_reserve_cash_buffer_disabled_when_pct_and_cost_zero(monkeypatch) -> None:
    executor = AIPortfolioExecutor(StubBroker(), allocated_capital=0.0)
    _enable_buffer(monkeypatch, pct=0.0, cost=0.0)

    # With both inputs zero the reserve is zero: the base is unchanged.
    assert executor._reserve_cash_buffer(100_000.0, 25) == pytest.approx(100_000.0)


def test_reserve_cash_buffer_never_negative(monkeypatch) -> None:
    executor = AIPortfolioExecutor(StubBroker(), allocated_capital=0.0)
    _enable_buffer(monkeypatch, pct=0.015, cost=1.0)

    # A fee estimate larger than the whole base floors the net base at 0.
    assert executor._reserve_cash_buffer(10.0, 1_000) == pytest.approx(0.0)


def test_execute_build_reserves_buffer(monkeypatch) -> None:
    _enable_buffer(monkeypatch, pct=0.015, cost=1.0)
    broker = StubBroker()
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000.0)
    stocks = [_stock("AAPL", 0.5), _stock("MSFT", 0.5)]

    results = executor.execute_build(stocks)

    # pct (1_500) dominates 2 * $1 -> net base 98_500. Whole-share flooring only
    # reduces deployment further, so the build never spends more than the net base
    # and leaves at least the reserve as cash.
    net_base = executor._reserve_cash_buffer(100_000.0, len(stocks))
    assert net_base == pytest.approx(98_500.0)
    assert _deployed(results) <= net_base + 1e-6
    # And it sized against the net base, not the full capital: deployment is within
    # one whole share (per ticker) of the net base.
    max_price = max(broker.get_quote(s.ticker).last for s in stocks)
    assert _deployed(results) > net_base - 2 * max_price


def test_execute_rebalance_reserves_buffer_from_flat(monkeypatch) -> None:
    _enable_buffer(monkeypatch, pct=0.015, cost=1.0)
    broker = StubBroker()
    executor = AIPortfolioExecutor(broker, allocated_capital=50_000.0)
    # Size against a grown live value (gains included); from flat so every order is
    # a buy and total deployment is directly observable.
    grown_value = 120_000.0
    targets = [_target("AAPL", 0.5), _target("MSFT", 0.5)]

    results = executor.execute_rebalance(
        targets=targets,
        current_positions={},
        base_capital=grown_value,
    )

    # 1.5% of 120_000 = 1_800 dominates 2 * $1, so sizing uses 118_200. The buys
    # never deploy more than the net base, so the session keeps a cash reserve
    # instead of overdrawing into negative unallocated cash.
    net_base = executor._reserve_cash_buffer(grown_value, len(targets))
    assert net_base == pytest.approx(118_200.0)
    assert _deployed(results) <= net_base + 1e-6


def test_buffer_leaves_crypto_only_and_market_closed_behavior_unchanged(
    monkeypatch,
) -> None:
    _enable_buffer(monkeypatch, pct=0.015, cost=1.0)

    # crypto_only still drops equities entirely, even with the buffer on.
    broker = StubBroker()
    executor = AIPortfolioExecutor(broker, allocated_capital=1_000_000.0)
    results = executor.execute_rebalance(
        targets=[_target("AAPL", 0.5), _target("BTC-USD", 0.5)],
        current_positions={},
        asset_classes=_MIXED,
        base_capital=30_000.0,
        crypto_only=True,
    )
    assert [r.ticker for r in results] == ["BTC-USD"]
    assert results[0].side == "long"

    # market_open=False still records equities as skipped, not sized down.
    broker2 = StubBroker()
    executor2 = AIPortfolioExecutor(broker2, allocated_capital=100_000.0)
    results2 = executor2.execute_rebalance(
        targets=[_target("AAPL", 1.0)],
        current_positions={},
        market_open=False,
    )
    assert results2[0].executed is False
    assert results2[0].reason == "equity market closed"


# --------------------------------------------------------------------------- #
# Rebalance: redeploy unexecutable target weight across executable targets
# --------------------------------------------------------------------------- #


class _QuoteControlBroker(StubBroker):
    """StubBroker with per-ticker price overrides and an unpriceable set.

    ``prices`` pins a ticker's quote (bid/ask/last) to an exact value so share
    math is deterministic; any ticker in ``unpriceable`` returns a quote with no
    usable price (``last``/``ask`` ``None``), simulating a listing the broker
    cannot price (e.g. a dot-suffixed foreign ticker).
    """

    def __init__(
        self,
        prices: dict[str, float] | None = None,
        unpriceable: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._prices = prices or {}
        self._unpriceable = set(unpriceable or ())

    def get_quote(
        self, symbol: str, asset_class: AssetClass = AssetClass.EQUITY
    ) -> Quote:  # type: ignore[override]
        if symbol in self._unpriceable:
            return Quote(symbol=symbol, bid=None, ask=None, last=None, volume=0)
        if symbol in self._prices:
            price = self._prices[symbol]
            return Quote(
                symbol=symbol,
                bid=price,
                ask=price,
                last=price,
                volume=1_000_000,
            )
        return super().get_quote(symbol, asset_class)


def test_rebalance_redeploys_unpriceable_target_weight() -> None:
    # ASML.AS cannot be priced; its 20% weight must be redeployed across AAPL and
    # MSFT rather than stranded as cash. Without redeployment each would buy 40
    # shares (weight 0.40 of $10k at $100); with it, each absorbs the freed weight
    # and buys 50 (effective weight 0.50), deploying the whole base.
    broker = _QuoteControlBroker(
        prices={"AAPL": 100.0, "MSFT": 100.0}, unpriceable={"ASML.AS"}
    )
    executor = AIPortfolioExecutor(broker, allocated_capital=10_000.0)

    results = executor.execute_rebalance(
        targets=[
            _target("AAPL", 0.40),
            _target("MSFT", 0.40),
            _target("ASML.AS", 0.20),
        ],
        current_positions={},
    )

    by_ticker = {r.ticker: r for r in results}
    assert by_ticker["AAPL"].executed is True
    assert by_ticker["AAPL"].shares == 50
    assert by_ticker["MSFT"].executed is True
    assert by_ticker["MSFT"].shares == 50
    # The unpriceable target is recorded, not silently dropped.
    assert by_ticker["ASML.AS"].executed is False
    assert by_ticker["ASML.AS"].reason == "No price available"
    # Invested = 50*100 + 50*100 = 10_000, the full base (buffer off in this suite).
    invested = by_ticker["AAPL"].shares * 100 + by_ticker["MSFT"].shares * 100
    assert invested == 10_000


def test_rebalance_redeployment_respects_reserved_cash_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Re-enable the buffer (the suite-wide fixture pins it off). Redeployment sizes
    # against net_base = base - buffer, so deployable cash is never driven below
    # the reserve.
    monkeypatch.setattr(settings, "REBALANCE_CASH_BUFFER_PCT", 0.02)
    monkeypatch.setattr(settings, "TRANSACTION_COST_USD", 0.0)
    broker = _QuoteControlBroker(
        prices={"AAPL": 100.0, "MSFT": 100.0}, unpriceable={"ASML.AS"}
    )
    base = 10_000.0
    executor = AIPortfolioExecutor(broker, allocated_capital=base)

    results = executor.execute_rebalance(
        targets=[
            _target("AAPL", 0.40),
            _target("MSFT", 0.40),
            _target("ASML.AS", 0.20),
        ],
        current_positions={},
    )

    by_ticker = {r.ticker: r for r in results}
    # net_base = 10_000 - 2% = 9_800; redeployed weight 0.5 each -> int(9800*0.5/100).
    assert by_ticker["AAPL"].shares == 49
    assert by_ticker["MSFT"].shares == 49
    invested = (by_ticker["AAPL"].shares + by_ticker["MSFT"].shares) * 100
    residual_cash = base - invested
    assert residual_cash >= base * 0.02  # reserve preserved


def test_rebalance_redeployment_respects_guardrail_caps() -> None:
    # ASML.AS (0.5, unpriceable) redeploys onto AAPL (0.4) and MSFT (0.1), which
    # would push AAPL to weight 0.8. A per-asset cap of 0.5 must still bind the
    # redeployed vector: AAPL is clamped to 0.5 and the excess flows to MSFT.
    broker = _QuoteControlBroker(
        prices={"AAPL": 100.0, "MSFT": 100.0}, unpriceable={"ASML.AS"}
    )
    executor = AIPortfolioExecutor(broker, allocated_capital=10_000.0)
    caps = GuardrailCaps(max_per_asset=0.5, max_per_class=1.0, max_invested=1.0)

    results = executor.execute_rebalance(
        targets=[
            _target("AAPL", 0.40),
            _target("MSFT", 0.10),
            _target("ASML.AS", 0.50),
        ],
        current_positions={},
        asset_classes={
            "AAPL": AssetClass.EQUITY,
            "MSFT": AssetClass.EQUITY,
            "ASML.AS": AssetClass.EQUITY,
        },
        caps=caps,
    )

    by_ticker = {r.ticker: r for r in results}
    # Capped at 0.5 each -> 50 shares, not AAPL's uncapped 0.8 -> 80 shares.
    assert by_ticker["AAPL"].shares == 50
    assert by_ticker["MSFT"].shares == 50


def test_rebalance_redeploys_too_small_target_and_records_it() -> None:
    # EXPENSIVE's 50% share of $10k ($5k) cannot fund one $100k share, so it is
    # unexecutable: its weight redeploys onto AAPL (which then buys the full base)
    # and EXPENSIVE is recorded as not executed rather than dropped silently.
    broker = _QuoteControlBroker(prices={"AAPL": 100.0, "EXPENSIVE": 100_000.0})
    executor = AIPortfolioExecutor(broker, allocated_capital=10_000.0)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 0.50), _target("EXPENSIVE", 0.50)],
        current_positions={},
    )

    by_ticker = {r.ticker: r for r in results}
    assert by_ticker["AAPL"].executed is True
    assert by_ticker["AAPL"].shares == 100  # weight redeployed from 0.5 to 1.0
    assert by_ticker["EXPENSIVE"].executed is False
    assert "too small" in by_ticker["EXPENSIVE"].reason.lower()


def test_rebalance_at_target_holding_is_silent_noop() -> None:
    # A held position already at its target produces a |delta| < 1 no-op. That is a
    # legitimate adjustment, NOT a "could not fund" failure, so it is not surfaced.
    broker = _QuoteControlBroker(prices={"AAPL": 100.0})
    broker.buy("AAPL", 50)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=5_000.0)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 1.0)],  # 5_000/100 = 50 shares == held
        current_positions=positions,
    )

    assert results == []


def test_rebalance_all_unexecutable_leaves_cash_without_failing() -> None:
    # No target can be priced: the run completes, places no order, and records every
    # target as not executed instead of raising.
    broker = _QuoteControlBroker(unpriceable={"AAPL", "MSFT"})
    executor = AIPortfolioExecutor(broker, allocated_capital=10_000.0)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 0.5), _target("MSFT", 0.5)],
        current_positions={},
    )

    assert len(results) == 2
    assert all(not r.executed for r in results)
    assert all(r.reason == "No price available" for r in results)


def test_rebalance_crypto_only_redeploys_within_crypto_scope() -> None:
    # Crypto-only weekend run: an unpriceable crypto target's weight redeploys onto
    # the other crypto targets, sized off the crypto budget, with no equity pulled
    # back in.
    broker = _QuoteControlBroker(
        prices={"BTC-USD": 100.0, "ETH-USD": 100.0}, unpriceable={"XRP-USD"}
    )
    classes = {
        "BTC-USD": AssetClass.CRYPTO,
        "ETH-USD": AssetClass.CRYPTO,
        "XRP-USD": AssetClass.CRYPTO,
    }
    executor = AIPortfolioExecutor(broker, allocated_capital=1_000_000.0)

    results = executor.execute_rebalance(
        targets=[
            _target("BTC-USD", 0.40),
            _target("ETH-USD", 0.40),
            _target("XRP-USD", 0.20),
        ],
        current_positions={},
        asset_classes=classes,
        base_capital=1_000.0,
        crypto_only=True,
    )

    by_ticker = {r.ticker: r for r in results}
    # Freed XRP weight -> BTC/ETH at 0.5 each: 1_000 * 0.5 / 100 = 5.0 units.
    assert by_ticker["BTC-USD"].shares == pytest.approx(5.0)
    assert by_ticker["ETH-USD"].shares == pytest.approx(5.0)
    assert by_ticker["XRP-USD"].executed is False


def test_rebalance_exits_held_ticker_absent_from_targets() -> None:
    # A ticker excluded from the agent's candidates is never re-targeted, so it has
    # target weight 0. The rebalance trade set is the union of held positions and
    # targets, so the held position is still exited (sold in full) via its quote —
    # the candidate exclusion does not prevent the exit.
    broker = _QuoteControlBroker(prices={"AAPL": 100.0, "ASML.AS": 100.0})
    broker.buy("ASML.AS", 10)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=10_000.0)

    results = executor.execute_rebalance(
        targets=[_target("AAPL", 1.0)],  # ASML.AS deliberately not a target
        current_positions=positions,
    )

    by_ticker = {r.ticker: r for r in results}
    assert by_ticker["ASML.AS"].side == "sell"
    assert by_ticker["ASML.AS"].executed is True
    assert by_ticker["ASML.AS"].shares == 10  # full exit
    assert "exit" in by_ticker["ASML.AS"].reason.lower()
