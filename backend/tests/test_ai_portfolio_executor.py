"""Tests for :class:`AIPortfolioExecutor` driving orders through a stub broker."""

from __future__ import annotations

import pytest

from cadence.ai_portfolio.agent import AIPortfolioStock, AITargetAllocation
from cadence.ai_portfolio.executor import AIPortfolioExecutor
from cadence.broker.base import OrderError
from cadence.broker.models import AssetClass, OrderType, Position, TimeInForce
from cadence.broker.stub import StubBroker


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
