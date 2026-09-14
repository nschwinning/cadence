"""Tests for :class:`AIPortfolioExecutor` driving orders through a stub broker."""

from __future__ import annotations

from cadence.ai_portfolio.agent import (
    AIPortfolioStock,
    ExistingHoldingEvaluation,
    NewStockRecommendation,
    PositionSide,
    RebalanceAction,
)
from cadence.ai_portfolio.executor import AIPortfolioExecutor
from cadence.broker.base import OrderError
from cadence.broker.models import OrderType, Position, TimeInForce
from cadence.broker.stub import StubBroker


def _stock(ticker: str, alloc: float, side: PositionSide = PositionSide.LONG) -> AIPortfolioStock:
    return AIPortfolioStock(
        ticker=ticker,
        company_name=ticker,
        side=side,
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
    ):  # type: ignore[override]
        if symbol == self._fail_ticker:
            raise OrderError(f"forced failure for {symbol}")
        return super().buy(symbol, quantity, order_type, limit_price, time_in_force)


def test_execute_build_sizes_positions_from_capital() -> None:
    broker = StubBroker()
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_build([_stock("AAPL", 0.5), _stock("MSFT", 0.5)])

    assert len(results) == 2
    assert all(r.executed for r in results)
    for r in results:
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


def test_execute_rebalance_closes_before_opening() -> None:
    broker = StubBroker()
    # Establish a held long position to close.
    broker.buy("AAPL", 10)
    positions = {p.symbol: p for p in broker.get_positions()}

    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)
    results = executor.execute_rebalance(
        evaluations=[
            ExistingHoldingEvaluation(
                ticker="AAPL",
                action=RebalanceAction.SELL,
                reasoning="exit",
                confidence=0.8,
            )
        ],
        new_recs=[
            NewStockRecommendation(
                ticker="MSFT",
                company_name="Microsoft",
                side=PositionSide.LONG,
                allocation_pct=0.3,
                investment_thesis="cloud",
                confidence=0.9,
            )
        ],
        current_positions=positions,
    )

    executed = [r for r in results if r.executed]
    assert executed[0].ticker == "AAPL"
    assert executed[0].side == "sell"
    assert executed[1].ticker == "MSFT"


def test_execute_rebalance_holds_are_noops() -> None:
    broker = StubBroker()
    broker.buy("AAPL", 5)
    positions = {p.symbol: p for p in broker.get_positions()}
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        evaluations=[
            ExistingHoldingEvaluation(
                ticker="AAPL",
                action=RebalanceAction.HOLD,
                reasoning="keep",
                confidence=0.9,
            )
        ],
        new_recs=[],
        current_positions=positions,
    )

    assert results == []


def test_execute_rebalance_skips_missing_position() -> None:
    broker = StubBroker()
    executor = AIPortfolioExecutor(broker, allocated_capital=100_000)

    results = executor.execute_rebalance(
        evaluations=[
            ExistingHoldingEvaluation(
                ticker="AAPL",
                action=RebalanceAction.SELL,
                reasoning="exit",
                confidence=0.8,
            )
        ],
        new_recs=[],
        current_positions={},
    )

    assert len(results) == 1
    assert results[0].executed is False
    assert results[0].reason == "No position to close"


def test_position_helper_import_available() -> None:
    # Sanity: the Position model used to size positions is importable.
    assert Position(symbol="X", quantity=0.0, avg_cost=0.0).symbol == "X"
