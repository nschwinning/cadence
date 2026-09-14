"""Executor for AI-managed portfolio trades.

Operates purely against the :class:`~cadence.broker.base.Broker` protocol. The
build sizes each long position from live quotes and the allocated capital.
Sizing is class-aware: equities are sized in whole shares (skipping sub-one-share
allocations), while crypto is sized in fractional units (skipping only allocations
below the brokerage minimum notional, :data:`MIN_CRYPTO_NOTIONAL_USD`). The
rebalance implements a **target-weight** model: it computes desired quantities
from the AI's target weights and trades the delta against the current positions
(buying increases, selling reductions and full exits). When the equities market
is closed, equity tickers are skipped while crypto continues to trade 24/7. Every
per-ticker order is wrapped in ``try/except`` so a single failure can't abort the
run; the outcome of each ticker is a :class:`TradeResult`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from cadence.ai_portfolio.agent import AIPortfolioStock, AITargetAllocation
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, OrderStatus, Position

logger = logging.getLogger(__name__)

#: Brokerage minimum tradable notional for crypto (USD). Allocations (or deltas)
#: worth less than this are skipped rather than sent as dust orders.
MIN_CRYPTO_NOTIONAL_USD = 1.0

#: Decimal places to round fractional crypto quantities to.
CRYPTO_QTY_PRECISION = 8


@dataclass
class TradeResult:
    """The outcome of attempting a single ticker's order during a build/rebalance."""

    ticker: str
    side: str
    shares: float
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

    def execute_build(
        self,
        stocks: list[AIPortfolioStock],
        asset_classes: dict[str, AssetClass] | None = None,
    ) -> list[TradeResult]:
        """Open each stock long, sizing from its normalized allocation and quote.

        ``asset_classes`` maps a ticker to its :class:`AssetClass`; tickers absent
        from the map default to :attr:`AssetClass.EQUITY`.
        """
        classes = asset_classes or {}
        total_alloc = sum(s.allocation_pct for s in stocks)
        results: list[TradeResult] = []

        for stock in stocks:
            cls = classes.get(stock.ticker, AssetClass.EQUITY)
            normalized_alloc = (
                stock.allocation_pct / total_alloc if total_alloc > 0 else 0.0
            )
            capital_for_stock = self.allocated_capital * normalized_alloc

            try:
                quote = self.broker.get_quote(stock.ticker, cls)
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

                if cls == AssetClass.CRYPTO:
                    qty = round(capital_for_stock / price, CRYPTO_QTY_PRECISION)
                    if qty <= 0 or qty * price < MIN_CRYPTO_NOTIONAL_USD:
                        results.append(
                            TradeResult(
                                ticker=stock.ticker,
                                side="long",
                                shares=0,
                                price=price,
                                executed=False,
                                reason=(
                                    f"Allocation ${capital_for_stock:.2f} below "
                                    f"min notional ${MIN_CRYPTO_NOTIONAL_USD:.2f}"
                                ),
                            )
                        )
                        continue
                else:
                    qty = float(int(capital_for_stock / price))
                    if qty < 1:
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

                order = self.broker.buy(stock.ticker, qty, asset_class=cls)
                fill_price = order.filled_price or price
                results.append(
                    TradeResult(
                        ticker=stock.ticker,
                        side="long",
                        shares=qty,
                        price=fill_price,
                        executed=True,
                        reason=f"Bought {qty} units",
                        order_id=order.order_id,
                        order_status=order.status,
                        filled_price=order.filled_price,
                    )
                )
                logger.info("AI build: long %s %s @ ~$%.2f", qty, stock.ticker, price)

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
        asset_classes: dict[str, AssetClass] | None = None,
        market_open: bool = True,
    ) -> list[TradeResult]:
        """Trade toward the AI's target weights, delta by delta.

        Target weights are normalized to sum 1 over the provided targets. Target
        quantities are sized off the executor's ``allocated_capital`` (the same
        base as build). For each ticker in the union of held positions and
        targets, the delta between target and current becomes a buy or a sell; a
        held ticker absent from targets is fully sold.

        Sizing is class-aware: equities use whole-share deltas (skip ``|delta| <
        1``), crypto uses fractional deltas (skip when the delta's notional is
        below :data:`MIN_CRYPTO_NOTIONAL_USD`). When ``market_open`` is ``False``,
        equity tickers are recorded as not executed ("equity market closed") and
        no order is placed, while crypto tickers trade normally.
        """
        classes = asset_classes or {}
        total_weight = sum(t.allocation_pct for t in targets)
        target_weight: dict[str, float] = {}
        for t in targets:
            norm = t.allocation_pct / total_weight if total_weight > 0 else 0.0
            target_weight[t.ticker] = target_weight.get(t.ticker, 0.0) + norm

        base_capital = self.allocated_capital
        tickers = sorted(set(current_positions) | set(target_weight))
        results: list[TradeResult] = []

        for ticker in tickers:
            cls = classes.get(ticker, AssetClass.EQUITY)
            pos = current_positions.get(ticker)
            weight = target_weight.get(ticker, 0.0)

            if not market_open and cls == AssetClass.EQUITY:
                results.append(
                    TradeResult(
                        ticker=ticker,
                        side="long" if weight > 0 else "sell",
                        shares=0,
                        price=None,
                        executed=False,
                        reason="equity market closed",
                    )
                )
                continue

            try:
                quote = self.broker.get_quote(ticker, cls)
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

                if cls == AssetClass.CRYPTO:
                    result = self._rebalance_crypto(
                        ticker, pos, weight, price, base_capital
                    )
                else:
                    result = self._rebalance_equity(
                        ticker, pos, weight, price, base_capital
                    )
                if result is not None:
                    results.append(result)

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

    def _rebalance_equity(
        self,
        ticker: str,
        pos: Position | None,
        weight: float,
        price: float,
        base_capital: float,
    ) -> TradeResult | None:
        """Whole-share delta trade for an equity ticker (skip ``|delta| < 1``)."""
        current_shares = int(pos.quantity) if pos else 0
        target_shares = int(base_capital * weight / price) if weight > 0 else 0
        delta = target_shares - current_shares

        if delta >= 1:
            order = self.broker.buy(ticker, delta, asset_class=AssetClass.EQUITY)
            fill_price = order.filled_price or price
            logger.info("AI rebalance: long %s %s", delta, ticker)
            return TradeResult(
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
        if delta <= -1:
            qty = min(-delta, current_shares)
            if qty < 1:
                return None
            order = self.broker.sell(ticker, qty, asset_class=AssetClass.EQUITY)
            fill_price = order.filled_price or price
            reason = (
                f"Sold {qty} shares (exit)"
                if target_shares == 0
                else f"Sold {qty} shares toward target"
            )
            logger.info("AI rebalance: sell %s %s", qty, ticker)
            return TradeResult(
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
        # |delta| < 1: no-op, no TradeResult recorded.
        return None

    def _rebalance_crypto(
        self,
        ticker: str,
        pos: Position | None,
        weight: float,
        price: float,
        base_capital: float,
    ) -> TradeResult | None:
        """Fractional delta trade for a crypto ticker (skip sub-min-notional deltas)."""
        current = pos.quantity if pos else 0.0
        target = (
            round(base_capital * weight / price, CRYPTO_QTY_PRECISION)
            if weight > 0
            else 0.0
        )
        delta = round(target - current, CRYPTO_QTY_PRECISION)

        if abs(delta) * price < MIN_CRYPTO_NOTIONAL_USD:
            # Below min notional (covers the near-zero delta no-op case too).
            return None

        if delta > 0:
            order = self.broker.buy(ticker, delta, asset_class=AssetClass.CRYPTO)
            fill_price = order.filled_price or price
            logger.info("AI rebalance: long %s %s", delta, ticker)
            return TradeResult(
                ticker=ticker,
                side="long",
                shares=delta,
                price=fill_price,
                executed=True,
                reason=f"Bought {delta} units toward target",
                order_id=order.order_id,
                order_status=order.status,
                filled_price=order.filled_price,
            )
        # delta < 0: sell the shortfall, capped at the held quantity (exit sells
        # the full current float when weight is 0).
        qty = round(min(-delta, current), CRYPTO_QTY_PRECISION)
        if qty <= 0:
            return None
        order = self.broker.sell(ticker, qty, asset_class=AssetClass.CRYPTO)
        fill_price = order.filled_price or price
        reason = (
            f"Sold {qty} units (exit)"
            if target == 0
            else f"Sold {qty} units toward target"
        )
        logger.info("AI rebalance: sell %s %s", qty, ticker)
        return TradeResult(
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
