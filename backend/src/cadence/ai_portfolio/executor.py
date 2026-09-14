"""Executor for AI-managed portfolio trades.

Ported faithfully from trading-bot's ``ai_portfolio_executor``. It operates purely
against the :class:`~cadence.broker.base.Broker` protocol — sizing each position
from live quotes and buying power, skipping sub-one-share allocations, and, on a
rebalance, closing positions before opening new ones. Every per-ticker order is
wrapped in ``try/except`` so a single failure can't abort the run; the outcome of
each ticker is returned as a :class:`TradeResult`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from cadence.ai_portfolio.agent import (
    AIPortfolioStock,
    ExistingHoldingEvaluation,
    NewStockRecommendation,
    PositionSide,
    RebalanceAction,
)
from cadence.broker.base import Broker
from cadence.broker.models import OrderStatus, Position

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """The outcome of attempting a single ticker's order during a build/rebalance."""

    ticker: str
    side: str
    shares: int
    price: float | None
    executed: bool
    reason: str
    order_id: str | None = None
    order_status: OrderStatus = OrderStatus.FILLED
    filled_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "side": self.side,
            "shares": self.shares,
            "price": self.price,
            "executed": self.executed,
            "reason": self.reason,
            "order_id": self.order_id,
            "order_status": self.order_status.value,
        }


class AIPortfolioExecutor:
    """Sizes and places AI portfolio orders through a :class:`Broker`."""

    def __init__(self, broker: Broker, allocated_capital: float) -> None:
        self.broker = broker
        self.allocated_capital = allocated_capital

    def execute_build(self, stocks: list[AIPortfolioStock]) -> list[TradeResult]:
        """Open each stock, sizing shares from its normalized allocation and quote."""
        total_alloc = sum(s.allocation_pct for s in stocks)
        results: list[TradeResult] = []

        for stock in stocks:
            normalized_alloc = (
                stock.allocation_pct / total_alloc if total_alloc > 0 else 0.0
            )
            capital_for_stock = self.allocated_capital * normalized_alloc

            try:
                quote = self.broker.get_quote(stock.ticker)
                price = quote.last or quote.ask
                if not price or price <= 0:
                    results.append(
                        TradeResult(
                            ticker=stock.ticker,
                            side=stock.side.value,
                            shares=0,
                            price=None,
                            executed=False,
                            reason="No price available",
                        )
                    )
                    continue

                shares = int(capital_for_stock / price)
                if shares < 1:
                    results.append(
                        TradeResult(
                            ticker=stock.ticker,
                            side=stock.side.value,
                            shares=0,
                            price=price,
                            executed=False,
                            reason=(
                                f"Allocation ${capital_for_stock:.0f} too small "
                                f"for price ${price:.2f}"
                            ),
                        )
                    )
                    continue

                if stock.side == PositionSide.LONG:
                    order = self.broker.buy(stock.ticker, shares)
                else:
                    order = self.broker.sell(stock.ticker, shares)

                fill_price = order.filled_price or price
                results.append(
                    TradeResult(
                        ticker=stock.ticker,
                        side=stock.side.value,
                        shares=shares,
                        price=fill_price,
                        executed=True,
                        reason=(
                            f"{'Bought' if stock.side == PositionSide.LONG else 'Shorted'} "
                            f"{shares} shares"
                        ),
                        order_id=order.order_id,
                        order_status=order.status,
                        filled_price=order.filled_price,
                    )
                )
                logger.info(
                    "AI build: %s %s %s @ ~$%.2f",
                    stock.side.value,
                    shares,
                    stock.ticker,
                    price,
                )

            except Exception as exc:  # noqa: BLE001 - one ticker must not abort the run
                logger.error("AI build failed for %s: %s", stock.ticker, exc)
                results.append(
                    TradeResult(
                        ticker=stock.ticker,
                        side=stock.side.value,
                        shares=0,
                        price=None,
                        executed=False,
                        reason=f"Order failed: {exc}",
                    )
                )

        return results

    def execute_rebalance(
        self,
        evaluations: list[ExistingHoldingEvaluation],
        new_recs: list[NewStockRecommendation],
        current_positions: dict[str, Position],
    ) -> list[TradeResult]:
        """Close sold/covered holdings first, then open any new recommendations."""
        results: list[TradeResult] = []

        # Phase 1: Close positions (sells and covers).
        for ev in evaluations:
            if ev.action == RebalanceAction.HOLD:
                continue

            pos = current_positions.get(ev.ticker)
            if not pos or pos.quantity == 0:
                results.append(
                    TradeResult(
                        ticker=ev.ticker,
                        side=ev.action.value,
                        shares=0,
                        price=None,
                        executed=False,
                        reason="No position to close",
                    )
                )
                continue

            try:
                qty = int(abs(pos.quantity))
                if ev.action == RebalanceAction.SELL:
                    order = self.broker.sell(ev.ticker, qty)
                    side_label = "sell"
                else:
                    order = self.broker.buy(ev.ticker, qty)
                    side_label = "cover"

                results.append(
                    TradeResult(
                        ticker=ev.ticker,
                        side=side_label,
                        shares=qty,
                        price=order.filled_price,
                        executed=True,
                        reason=(
                            f"{'Sold' if side_label == 'sell' else 'Covered'} {qty} "
                            f"shares — {ev.reasoning}"
                        ),
                        order_id=order.order_id,
                        order_status=order.status,
                        filled_price=order.filled_price,
                    )
                )
                logger.info("AI rebalance: %s %s %s", side_label, qty, ev.ticker)

            except Exception as exc:  # noqa: BLE001 - one ticker must not abort the run
                logger.error("AI rebalance close failed for %s: %s", ev.ticker, exc)
                results.append(
                    TradeResult(
                        ticker=ev.ticker,
                        side=ev.action.value,
                        shares=0,
                        price=None,
                        executed=False,
                        reason=f"Order failed: {exc}",
                    )
                )

        # Phase 2: Open new positions.
        if not new_recs:
            return results

        account = self.broker.get_account_info()
        available = account.buying_power

        for rec in new_recs:
            capital_for_stock = min(self.allocated_capital * rec.allocation_pct, available)

            try:
                quote = self.broker.get_quote(rec.ticker)
                price = quote.last or quote.ask
                if not price or price <= 0:
                    results.append(
                        TradeResult(
                            ticker=rec.ticker,
                            side=rec.side.value,
                            shares=0,
                            price=None,
                            executed=False,
                            reason="No price available",
                        )
                    )
                    continue

                shares = int(capital_for_stock / price)
                if shares < 1:
                    results.append(
                        TradeResult(
                            ticker=rec.ticker,
                            side=rec.side.value,
                            shares=0,
                            price=price,
                            executed=False,
                            reason="Insufficient capital for 1 share",
                        )
                    )
                    continue

                if rec.side == PositionSide.LONG:
                    order = self.broker.buy(rec.ticker, shares)
                else:
                    order = self.broker.sell(rec.ticker, shares)

                fill_price = order.filled_price or price
                results.append(
                    TradeResult(
                        ticker=rec.ticker,
                        side=rec.side.value,
                        shares=shares,
                        price=fill_price,
                        executed=True,
                        reason=(
                            f"{'Bought' if rec.side == PositionSide.LONG else 'Shorted'} "
                            f"{shares} shares — {rec.investment_thesis[:100]}"
                        ),
                        order_id=order.order_id,
                        order_status=order.status,
                        filled_price=order.filled_price,
                    )
                )
                available -= shares * price
                logger.info(
                    "AI rebalance: %s %s %s @ ~$%.2f",
                    rec.side.value,
                    shares,
                    rec.ticker,
                    price,
                )

            except Exception as exc:  # noqa: BLE001 - one ticker must not abort the run
                logger.error("AI rebalance add failed for %s: %s", rec.ticker, exc)
                results.append(
                    TradeResult(
                        ticker=rec.ticker,
                        side=rec.side.value,
                        shares=0,
                        price=None,
                        executed=False,
                        reason=f"Order failed: {exc}",
                    )
                )

        return results
