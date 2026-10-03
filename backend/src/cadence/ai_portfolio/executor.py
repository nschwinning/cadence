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
from collections import defaultdict
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

#: Iteration ceiling / convergence tolerance for the guardrail water-filling loop.
_GUARDRAIL_MAX_ITERATIONS = 100
_GUARDRAIL_EPSILON = 1e-9


@dataclass(frozen=True)
class GuardrailCaps:
    """The deterministic portfolio risk caps enforced on a target-weight vector.

    All values are fractions in ``(0, 1]``; a value of ``1.0`` is a no-op for that
    cap. The per-asset and per-class caps bound concentration; ``max_invested``
    bounds how much of the allocated capital is deployed (the remainder is cash).
    The minimum-position floor is *not* here — it cannot be enforced by clamping
    (see the proposal) and is instructed/surfaced elsewhere.
    """

    max_per_asset: float
    max_per_class: float
    max_invested: float


def enforce_guardrails(
    weights: dict[str, float],
    asset_classes: dict[str, AssetClass],
    caps: GuardrailCaps,
) -> dict[str, float]:
    """Clamp, redistribute, and scale a target-weight vector to obey ``caps``.

    Returns a new ``{ticker: weight}`` mapping in which no single ticker exceeds
    ``caps.max_per_asset``, no asset class exceeds ``caps.max_per_class``, and the
    total invested fraction does not exceed ``caps.max_invested`` — the remainder is
    the enforced cash buffer. Only positive input weights participate; the input is
    first normalized to sum 1.

    Enforcement is an iterative water-filling fixed point: over-cap weight is removed
    and redistributed proportionally to holdings still below their caps, alternating
    the per-asset and per-class passes until stable, then a terminal projection
    (per-asset clamp followed by scaling any still-over class down) guarantees a
    feasible vector even if the loop did not converge. When the caps cannot absorb the
    full capital (e.g. ``max_per_asset × count < 1``), the shortfall simply remains as
    cash rather than forcing any weight past a cap.
    """
    positive = {t: w for t, w in weights.items() if w > 0}
    total = sum(positive.values())
    if total <= 0:
        return {t: 0.0 for t in weights}

    asset_cap = caps.max_per_asset
    class_cap = caps.max_per_class
    w = {t: v / total for t, v in positive.items()}

    for _ in range(_GUARDRAIL_MAX_ITERATIONS):
        before = dict(w)
        w = _apply_asset_cap(w, asset_cap)
        w = _apply_class_cap(w, asset_classes, class_cap, asset_cap)
        if _max_abs_diff(before, w) < _GUARDRAIL_EPSILON:
            break

    # Terminal projection: guarantees feasibility regardless of loop convergence.
    # A per-asset clamp then a scale-down of any over class never lifts a weight
    # back above the per-asset cap (scaling multiplies by <= 1), so both caps hold.
    w = {t: min(v, asset_cap) for t, v in w.items()}
    w = _scale_over_classes(w, asset_classes, class_cap)

    invested = sum(w.values())
    if invested > caps.max_invested + _GUARDRAIL_EPSILON:
        factor = caps.max_invested / invested
        w = {t: v * factor for t, v in w.items()}

    return w


def _apply_asset_cap(weights: dict[str, float], cap: float) -> dict[str, float]:
    """Clamp each weight to ``cap``, redistributing excess to under-cap holdings."""
    w = dict(weights)
    for _ in range(_GUARDRAIL_MAX_ITERATIONS):
        over = [t for t in w if w[t] > cap + _GUARDRAIL_EPSILON]
        if not over:
            break
        excess = sum(w[t] - cap for t in over)
        for t in over:
            w[t] = cap
        under = [t for t in w if w[t] < cap - _GUARDRAIL_EPSILON]
        if not under or excess <= _GUARDRAIL_EPSILON:
            break  # no headroom to place the excess; it becomes cash
        pool = sum(w[t] for t in under)
        if pool <= _GUARDRAIL_EPSILON:
            share = excess / len(under)
            for t in under:
                w[t] += share
        else:
            for t in under:
                w[t] += excess * (w[t] / pool)
    return w


def _apply_class_cap(
    weights: dict[str, float],
    asset_classes: dict[str, AssetClass],
    class_cap: float,
    asset_cap: float,
) -> dict[str, float]:
    """Scale over-cap classes down, redistributing freed weight to under classes."""
    w = dict(weights)
    for _ in range(_GUARDRAIL_MAX_ITERATIONS):
        class_sum: dict[AssetClass, float] = defaultdict(float)
        for t, v in w.items():
            class_sum[asset_classes.get(t, AssetClass.EQUITY)] += v
        over = {c for c, s in class_sum.items() if s > class_cap + _GUARDRAIL_EPSILON}
        if not over:
            break
        freed = 0.0
        for c in over:
            factor = class_cap / class_sum[c]
            for t in [k for k in w if asset_classes.get(k, AssetClass.EQUITY) == c]:
                freed += w[t] * (1 - factor)
                w[t] *= factor
        recipients = [
            t
            for t in w
            if asset_classes.get(t, AssetClass.EQUITY) not in over
            and w[t] < asset_cap - _GUARDRAIL_EPSILON
        ]
        if not recipients or freed <= _GUARDRAIL_EPSILON:
            break  # no headroom in other classes; freed weight becomes cash
        pool = sum(w[t] for t in recipients)
        if pool <= _GUARDRAIL_EPSILON:
            share = freed / len(recipients)
            for t in recipients:
                w[t] += share
        else:
            for t in recipients:
                w[t] += freed * (w[t] / pool)
    return w


def _scale_over_classes(
    weights: dict[str, float],
    asset_classes: dict[str, AssetClass],
    class_cap: float,
) -> dict[str, float]:
    """Scale any class whose weight exceeds ``class_cap`` down to it (no redistribute)."""
    class_sum: dict[AssetClass, float] = defaultdict(float)
    for t, v in weights.items():
        class_sum[asset_classes.get(t, AssetClass.EQUITY)] += v
    w = dict(weights)
    for c, s in class_sum.items():
        if s > class_cap + _GUARDRAIL_EPSILON:
            factor = class_cap / s
            for t in [k for k in w if asset_classes.get(k, AssetClass.EQUITY) == c]:
                w[t] *= factor
    return w


def _max_abs_diff(a: dict[str, float], b: dict[str, float]) -> float:
    """Largest per-key absolute difference between two weight maps."""
    keys = set(a) | set(b)
    return max((abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys), default=0.0)


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

    def to_stats_dict(self) -> dict[str, Any]:
        """Full serialization including ``filled_price`` for offline-learning stats.

        Superset of :meth:`to_dict` (which omits ``filled_price``); used for the
        run's ``run_stats`` payload, never for the UI-facing ``actions_taken``.
        """
        return {**self.to_dict(), "filled_price": self.filled_price}


class AIPortfolioExecutor:
    """Sizes and places AI portfolio orders through a :class:`Broker` (long-only)."""

    def __init__(self, broker: Broker, allocated_capital: float) -> None:
        self.broker = broker
        self.allocated_capital = allocated_capital

    def execute_build(
        self,
        stocks: list[AIPortfolioStock],
        asset_classes: dict[str, AssetClass] | None = None,
        caps: GuardrailCaps | None = None,
    ) -> list[TradeResult]:
        """Open each stock long, sizing from its normalized allocation and quote.

        ``asset_classes`` maps a ticker to its :class:`AssetClass`; tickers absent
        from the map default to :attr:`AssetClass.EQUITY`. When ``caps`` is provided
        (the session opted into the risk guardrails), the AI's allocations are first
        run through :func:`enforce_guardrails` so no position exceeds the per-asset
        cap, no class exceeds the per-class cap, and the invested fraction is bounded
        (remainder held as cash); when ``caps`` is ``None`` the raw normalized
        allocations are used unchanged.
        """
        classes = asset_classes or {}
        results: list[TradeResult] = []

        if caps is None:
            total_alloc = sum(s.allocation_pct for s in stocks)
            for stock in stocks:
                cls = classes.get(stock.ticker, AssetClass.EQUITY)
                normalized = (
                    stock.allocation_pct / total_alloc if total_alloc > 0 else 0.0
                )
                results.append(
                    self._open_long(
                        stock.ticker, cls, self.allocated_capital * normalized
                    )
                )
            return results

        raw: dict[str, float] = {}
        order: list[str] = []
        for stock in stocks:
            if stock.ticker not in raw:
                order.append(stock.ticker)
            raw[stock.ticker] = raw.get(stock.ticker, 0.0) + max(
                stock.allocation_pct, 0.0
            )
        weights = enforce_guardrails(raw, classes, caps)
        for ticker in order:
            cls = classes.get(ticker, AssetClass.EQUITY)
            results.append(
                self._open_long(
                    ticker, cls, self.allocated_capital * weights.get(ticker, 0.0)
                )
            )
        return results

    def _open_long(
        self, ticker: str, cls: AssetClass, capital_for_stock: float
    ) -> TradeResult:
        """Size ``capital_for_stock`` into a whole/fractional long and place the buy."""
        try:
            quote = self.broker.get_quote(ticker, cls)
            price = quote.last or quote.ask
            if not price or price <= 0:
                return TradeResult(
                    ticker=ticker,
                    side="long",
                    shares=0,
                    price=None,
                    executed=False,
                    reason="No price available",
                )

            if cls == AssetClass.CRYPTO:
                qty = round(capital_for_stock / price, CRYPTO_QTY_PRECISION)
                if qty <= 0 or qty * price < MIN_CRYPTO_NOTIONAL_USD:
                    return TradeResult(
                        ticker=ticker,
                        side="long",
                        shares=0,
                        price=price,
                        executed=False,
                        reason=(
                            f"Allocation ${capital_for_stock:.2f} below "
                            f"min notional ${MIN_CRYPTO_NOTIONAL_USD:.2f}"
                        ),
                    )
            else:
                qty = float(int(capital_for_stock / price))
                if qty < 1:
                    return TradeResult(
                        ticker=ticker,
                        side="long",
                        shares=0,
                        price=price,
                        executed=False,
                        reason=(
                            f"Allocation ${capital_for_stock:.0f} too small "
                            f"for price ${price:.2f}"
                        ),
                    )

            o = self.broker.buy(ticker, qty, asset_class=cls)
            fill_price = o.filled_price or price
            logger.info("AI build: long %s %s @ ~$%.2f", qty, ticker, price)
            return TradeResult(
                ticker=ticker,
                side="long",
                shares=qty,
                price=fill_price,
                executed=True,
                reason=f"Bought {qty} units",
                order_id=o.order_id,
                order_status=o.status,
                filled_price=o.filled_price,
            )

        except Exception as exc:  # noqa: BLE001 - one ticker must not abort the run
            logger.error("AI build failed for %s: %s", ticker, exc)
            return TradeResult(
                ticker=ticker,
                side="long",
                shares=0,
                price=None,
                executed=False,
                reason=f"Order failed: {exc}",
            )

    def execute_rebalance(
        self,
        targets: list[AITargetAllocation],
        current_positions: dict[str, Position],
        asset_classes: dict[str, AssetClass] | None = None,
        market_open: bool = True,
        caps: GuardrailCaps | None = None,
        base_capital: float | None = None,
        crypto_only: bool = False,
    ) -> list[TradeResult]:
        """Trade toward the AI's target weights, delta by delta.

        Target weights are normalized to sum 1 over the provided targets. Target
        quantities are sized off ``base_capital`` — the session's current
        marked-to-market value at rebalance time — so realised and unrealised
        gains are redeployed into the target allocation and losses size the
        targets down. When ``base_capital`` is ``None`` the executor's
        ``allocated_capital`` is used (the build-time base), preserving the
        previous behaviour for any caller that does not pass a live base. For
        each ticker in the union of held positions and targets, the delta between
        target and current becomes a buy or a sell; a held ticker absent from
        targets is fully sold.

        When ``crypto_only`` is set (the weekend crypto-only run), equities are
        excluded from BOTH the targets and the current positions before anything
        else, so no equity order is ever placed and no held equity is sold (design
        D3); the crypto weights are then normalized among themselves and sized off
        ``base_capital`` (the crypto budget). This is a hard guarantee at the
        executor boundary, independent of how the caller scoped its inputs.

        When ``caps`` is provided (the session opted into the risk guardrails), the
        normalized target weights are run through :func:`enforce_guardrails` before
        sizing so no ticker exceeds the per-asset cap, no class exceeds the per-class
        cap, and the invested fraction is bounded (remainder held as cash); when
        ``caps`` is ``None`` the raw normalized weights are used unchanged.

        Sizing is class-aware: equities use whole-share deltas (skip ``|delta| <
        1``), crypto uses fractional deltas (skip when the delta's notional is
        below :data:`MIN_CRYPTO_NOTIONAL_USD`). When ``market_open`` is ``False``,
        equity tickers are recorded as not executed ("equity market closed") and
        no order is placed, while crypto tickers trade normally.
        """
        classes = asset_classes or {}
        if crypto_only:
            # Hard guarantee at the executor boundary (design D3): drop every
            # equity from both the targets and the held positions so no equity
            # order is placed and no held equity is sold. Crypto weights then
            # normalize among themselves below and size off ``base_capital``.
            targets = [
                t
                for t in targets
                if classes.get(t.ticker, AssetClass.EQUITY) == AssetClass.CRYPTO
            ]
            current_positions = {
                ticker: pos
                for ticker, pos in current_positions.items()
                if classes.get(ticker, AssetClass.EQUITY) == AssetClass.CRYPTO
            }
        total_weight = sum(t.allocation_pct for t in targets)
        target_weight: dict[str, float] = {}
        for t in targets:
            norm = t.allocation_pct / total_weight if total_weight > 0 else 0.0
            target_weight[t.ticker] = target_weight.get(t.ticker, 0.0) + norm

        if caps is not None:
            target_weight = enforce_guardrails(target_weight, classes, caps)

        base = self.allocated_capital if base_capital is None else base_capital
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
                        ticker, pos, weight, price, base
                    )
                else:
                    result = self._rebalance_equity(
                        ticker, pos, weight, price, base
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

    def execute_close(
        self,
        positions: dict[str, Position],
        asset_classes: dict[str, AssetClass] | None = None,
    ) -> list[TradeResult]:
        """Liquidate every held position in full, regardless of market hours.

        Used by the close-portfolio flow: each position with a non-zero quantity is
        fully sold (equities in whole shares, crypto fractionally). Unlike
        :meth:`execute_rebalance`, there is no market-open guard — a sell is always
        submitted (real Alpaca queues an equity market order for the next open; the
        stub fills immediately). Positions are processed in ticker order and one
        ticker's failure is recorded as not executed without aborting the rest.
        """
        classes = asset_classes or {}
        results: list[TradeResult] = []

        for ticker in sorted(positions):
            pos = positions[ticker]
            if not pos.quantity:
                continue
            cls = classes.get(ticker, AssetClass.EQUITY)
            try:
                quote = self.broker.get_quote(ticker, cls)
                price = quote.last or quote.ask
                if cls == AssetClass.CRYPTO:
                    qty = round(abs(pos.quantity), CRYPTO_QTY_PRECISION)
                else:
                    qty = float(int(abs(pos.quantity)))
                if qty <= 0:
                    results.append(
                        TradeResult(
                            ticker=ticker,
                            side="sell",
                            shares=0,
                            price=price,
                            executed=False,
                            reason="Position below one tradable unit",
                        )
                    )
                    continue

                order = self.broker.sell(ticker, qty, asset_class=cls)
                fill_price = order.filled_price or price
                logger.info("AI close: sell %s %s", qty, ticker)
                results.append(
                    TradeResult(
                        ticker=ticker,
                        side="sell",
                        shares=qty,
                        price=fill_price,
                        executed=True,
                        reason=f"Closed {qty} units (exit)",
                        order_id=order.order_id,
                        order_status=order.status,
                        filled_price=order.filled_price,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - one ticker must not abort the run
                logger.error("AI close failed for %s: %s", ticker, exc)
                results.append(
                    TradeResult(
                        ticker=ticker,
                        side="sell",
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
