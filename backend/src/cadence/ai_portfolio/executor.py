"""Executor for AI-managed portfolio trades.

Operates purely against the :class:`~cadence.broker.base.Broker` protocol. The
build sizes each long position from live quotes and the allocated capital,
skipping sub-one-share allocations. The rebalance implements a **target-weight**
model: it computes desired share counts from the AI's target weights and trades
the delta against the current positions (buying increases, selling reductions and
full exits). Every per-ticker order is wrapped in ``try/except`` so a single
failure can't abort the run; the outcome of each ticker is a :class:`TradeResult`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from cadence.ai_portfolio.agent import AIPortfolioStock, AITargetAllocation
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
    """Sizes and places AI portfolio orders through a :class:`Broker` (long-only)."""

    def __init__(self, broker: Broker, allocated_capital: float) -> None:
        self.broker = broker
        self.allocated_capital = allocated_capital

    def execute_build(self, stocks: list[AIPortfolioStock]) -> list[TradeResult]:
        """Open each stock long, sizing shares from its normalized allocation and quote."""
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
                            side="long",
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
                            side="long",
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

                order = self.broker.buy(stock.ticker, shares)
                fill_price = order.filled_price or price
                results.append(
                    TradeResult(
                        ticker=stock.ticker,
                        side="long",
                        shares=shares,
                        price=fill_price,
                        executed=True,
                        reason=f"Bought {shares} shares",
                        order_id=order.order_id,
                        order_status=order.status,
                        filled_price=order.filled_price,
                    )
                )
                logger.info("AI build: long %s %s @ ~$%.2f", shares, stock.ticker, price)

            except Exception as exc:  # noqa: BLE001 - one ticker must not abort the run
                logger.error("AI build failed for %s: %s", stock.ticker, exc)
                results.append(
                    TradeResult(
                        ticker=stock.ticker,
                        side="long",
                        shares=0,
                        price=None,
                        executed=False,
                        reason=f"Order failed: {exc}",
                    )
                )

        return results

    def execute_rebalance(
        self,
        targets: list[AITargetAllocation],
        current_positions: dict[str, Position],
    ) -> list[TradeResult]:
        """Trade toward the AI's target weights, share-delta by share-delta.

        Target weights are normalized to sum 1 over the provided targets. Target
        shares are sized off the executor's ``allocated_capital`` (the same base as
        build). For each ticker in the union of held positions and targets, the
        delta between target and current shares becomes a buy (``delta >= 1``) or a
        sell (``delta <= -1``); a held ticker absent from targets is fully sold.
        """
        total_weight = sum(t.allocation_pct for t in targets)
        target_weight: dict[str, float] = {}
        for t in targets:
            norm = t.allocation_pct / total_weight if total_weight > 0 else 0.0
            target_weight[t.ticker] = target_weight.get(t.ticker, 0.0) + norm

        base_capital = self.allocated_capital
        tickers = sorted(set(current_positions) | set(target_weight))
        results: list[TradeResult] = []

        for ticker in tickers:
            pos = current_positions.get(ticker)
            current_shares = int(pos.quantity) if pos else 0
            weight = target_weight.get(ticker, 0.0)

            try:
                quote = self.broker.get_quote(ticker)
                price = quote.last or quote.ask
                if not price or price <= 0:
                    results.append(
                        TradeResult(
                            ticker=ticker,
                            side="long" if weight > 0 else "sell",
                            shares=0,
                            price=None,
                            executed=False,
                            reason="No price available",
                        )
                    )
                    continue

                target_shares = int(base_capital * weight / price) if weight > 0 else 0
                delta = target_shares - current_shares

                if delta >= 1:
                    order = self.broker.buy(ticker, delta)
                    fill_price = order.filled_price or price
                    results.append(
                        TradeResult(
                            ticker=ticker,
                            side="long",
                            shares=delta,
                            price=fill_price,
                            executed=True,
                            reason=f"Bought {delta} shares toward target",
                            order_id=order.order_id,
                            order_status=order.status,
                            filled_price=order.filled_price,
                        )
                    )
                    logger.info("AI rebalance: long %s %s", delta, ticker)
                elif delta <= -1:
                    qty = min(-delta, current_shares)
                    if qty < 1:
                        continue
                    order = self.broker.sell(ticker, qty)
                    fill_price = order.filled_price or price
                    reason = (
                        f"Sold {qty} shares (exit)"
                        if target_shares == 0
                        else f"Sold {qty} shares toward target"
                    )
                    results.append(
                        TradeResult(
                            ticker=ticker,
                            side="sell",
                            shares=qty,
                            price=fill_price,
                            executed=True,
                            reason=reason,
                            order_id=order.order_id,
                            order_status=order.status,
                            filled_price=order.filled_price,
                        )
                    )
                    logger.info("AI rebalance: sell %s %s", qty, ticker)
                # |delta| < 1: no-op, no TradeResult recorded.

            except Exception as exc:  # noqa: BLE001 - one ticker must not abort the run
                logger.error("AI rebalance failed for %s: %s", ticker, exc)
                results.append(
                    TradeResult(
                        ticker=ticker,
                        side="long" if weight > 0 else "sell",
                        shares=0,
                        price=None,
                        executed=False,
                        reason=f"Order failed: {exc}",
                    )
                )

        return results
