"""Executor for AI-managed portfolio trades.

Operates purely against the :class:`~cadence.broker.base.Broker` protocol. The
build sizes each long position from live quotes and the allocated capital.
Sizing is class- and fractionability-aware: crypto and equities the brokerage lists
as *fractionable* are sized in fractional units (skipping only allocations below the
brokerage minimum notional, :data:`MIN_CRYPTO_NOTIONAL_USD` /
:data:`MIN_EQUITY_NOTIONAL_USD`), while non-fractionable (or unknown) equities are
sized in whole shares (skipping sub-one-share allocations). The
rebalance implements a **target-weight** model: it computes desired quantities
from the AI's target weights and trades the delta against the current positions
(buying increases, selling reductions and full exits). When the equities market
is closed, equity tickers are skipped while crypto continues to trade 24/7. Every
per-ticker order is wrapped in ``try/except`` so a single failure can't abort the
run; the outcome of each ticker is a :class:`TradeResult`.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from cadence.ai_portfolio.agent import AIPortfolioStock, AITargetAllocation
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, OrderStatus, Position
from cadence.config import settings

#: Order statuses that count as settled for the sell→buy fill gate. A rejected or
#: cancelled sell is terminal too, so it never strands the run (house idiom from
#: the archived ``defer-rebalance-until-build-orders-filled`` change).
_TERMINAL_ORDER_STATUSES = frozenset(
    {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}
)

logger = logging.getLogger(__name__)

#: Brokerage minimum tradable notional for crypto (USD). Allocations (or deltas)
#: worth less than this are skipped rather than sent as dust orders.
MIN_CRYPTO_NOTIONAL_USD = 1.0

#: Decimal places to round fractional crypto quantities to.
CRYPTO_QTY_PRECISION = 8

#: Brokerage minimum tradable notional for fractionable equities (USD). An equity
#: allocation (or rebalance delta) worth less than this is skipped rather than sent
#: as a dust order — the fractional analogue of the old "less than one whole share"
#: skip, which now applies only to non-fractionable equities.
MIN_EQUITY_NOTIONAL_USD = 1.0

#: Decimal places to round fractional equity quantities to. Alpaca accepts up to 9;
#: 6 is ample for sizing and keeps float noise from generating dust orders.
EQUITY_QTY_PRECISION = 6

#: Iteration ceiling / convergence tolerance for the guardrail water-filling loop.
_GUARDRAIL_MAX_ITERATIONS = 100
_GUARDRAIL_EPSILON = 1e-9

#: Iteration ceiling for the unexecutable-weight redeployment loop. Each pass
#: removes at most one target, so the number of targets upper-bounds it; the cap
#: is a safety net against a pathological input.
_REDEPLOY_MAX_ITERATIONS = 100


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


@dataclass(frozen=True)
class _OrderIntent:
    """A sized, side-resolved rebalance order that has not been submitted yet.

    The rebalance decides and sizes every ticker into an intent first, then
    submits all sells before any buys (gating the buys on the sells' fills). The
    ``reason`` is the human-readable text carried verbatim onto the resulting
    :class:`TradeResult`; ``price`` is the reference quote used as the fill-price
    fallback when the broker reports no fill price (async brokers).
    """

    ticker: str
    asset_class: AssetClass
    side: str  # "long" (buy) or "sell"
    quantity: float
    price: float
    reason: str


class AIPortfolioExecutor:
    """Sizes and places AI portfolio orders through a :class:`Broker` (long-only)."""

    def __init__(self, broker: Broker, allocated_capital: float) -> None:
        self.broker = broker
        self.allocated_capital = allocated_capital
        # Set by ``execute_rebalance`` when a run is skipped as a no-op (a buy-only
        # plan with no deployable unallocated cash). The caller reads it to record a
        # SKIPPED run instead of applying trades.
        self.skipped_noop = False

    def _reserve_cash_buffer(self, base: float, candidate_count: int) -> float:
        """Shrink the sizing ``base`` by the reserved cash buffer.

        The reserve is the GREATER of a configured percentage of ``base`` and the
        estimated total trade fees for the run (``candidate_count`` orders, an
        upper bound of one per candidate ticker, times the per-trade transaction
        cost). Reducing the base before any target weight is applied keeps a
        fully invested target from deploying 100% of the session's value and then
        overdrawing on fees and fill slippage, so unallocated cash stays
        non-negative. Returns the net base, floored at 0. When both the buffer
        percentage and the transaction cost are 0 the reserve is 0 and the base
        is unchanged.
        """
        pct_reserve = base * settings.REBALANCE_CASH_BUFFER_PCT
        fee_reserve = max(0, candidate_count) * settings.TRANSACTION_COST_USD
        reserve = max(pct_reserve, fee_reserve)
        return max(base - reserve, 0.0)

    def _redeploy_target_weights(
        self,
        priced_weights: dict[str, float],
        min_notionals: dict[str, float],
        net_base: float,
        ceiling: float,
    ) -> tuple[dict[str, float], set[str]]:
        """Redistribute unexecutable target weight across the executable targets.

        ``priced_weights`` maps each priceable target (positive weight only) to its
        normalized weight; ``min_notionals`` maps a ticker to the minimum tradable
        notional at the current quote (one share's price for an equity, the minimum
        crypto notional for a crypto); ``net_base`` is the buffer-reduced sizing
        base; ``ceiling`` is the total weight to deploy across the survivors — the
        sum of every non-market-closed target's weight, so weight freed by
        unpriceable and too-small targets is redeployed but market-closed equity
        weight (absent from ``priced_weights`` and excluded from ``ceiling``) stays
        cash.

        Each pass rescales the surviving weights to sum to ``ceiling`` and checks
        whether every survivor can fund its minimum tradable amount against
        ``net_base``. If any cannot, the single smallest-weight unfundable target is
        removed (its weight flows to the rest on the next rescale) and the pass
        repeats; removing the smallest first lets the remaining weight concentrate
        enough to clear the threshold, so a set that would strand as cash if all
        unfundable targets were dropped at once can still deploy. The loop ends when
        every survivor is fundable, the set empties, or the iteration cap is hit.

        Returns ``(final_weights, too_small)`` where ``final_weights`` sums to at
        most ``ceiling`` (so deployment never exceeds the buffer-reduced base, and
        the reserved buffer is preserved) and ``too_small`` is the set of priceable
        targets removed for affordability.
        """
        working = dict(priced_weights)
        too_small: set[str] = set()

        for _ in range(_REDEPLOY_MAX_ITERATIONS):
            subtotal = sum(working.values())
            if subtotal <= 0.0:
                return {}, too_small
            scale = ceiling / subtotal
            scaled = {t: w * scale for t, w in working.items()}
            unfundable = [
                t for t, w in scaled.items() if net_base * w < min_notionals[t]
            ]
            if not unfundable:
                return scaled, too_small
            worst = min(unfundable, key=lambda t: scaled[t])
            too_small.add(worst)
            del working[worst]

        subtotal = sum(working.values())
        if subtotal <= 0.0:
            return {}, too_small
        scale = ceiling / subtotal
        return {t: w * scale for t, w in working.items()}, too_small

    def execute_build(
        self,
        stocks: list[AIPortfolioStock],
        asset_classes: dict[str, AssetClass] | None = None,
        caps: GuardrailCaps | None = None,
        fractionable: dict[str, bool] | None = None,
    ) -> list[TradeResult]:
        """Open each stock long, sizing from its normalized allocation and quote.

        ``asset_classes`` maps a ticker to its :class:`AssetClass`; tickers absent
        from the map default to :attr:`AssetClass.EQUITY`. ``fractionable`` maps a
        ticker to whether the brokerage lists it as fractionable; a ticker mapping to
        ``True`` is sized in fractional shares, while ``False``/absent (unknown) keeps
        the whole-share behaviour. When ``caps`` is provided
        (the session opted into the risk guardrails), the AI's allocations are first
        run through :func:`enforce_guardrails` so no position exceeds the per-asset
        cap, no class exceeds the per-class cap, and the invested fraction is bounded
        (remainder held as cash); when ``caps`` is ``None`` the raw normalized
        allocations are used unchanged.
        """
        classes = asset_classes or {}
        frac = fractionable or {}
        results: list[TradeResult] = []

        # Reserve a cash buffer so the build does not deploy the full allocated
        # capital and then overdraw on per-trade fees / fill slippage. At most
        # one order is placed per stock, so ``len(stocks)`` upper-bounds the fees.
        net_base = self._reserve_cash_buffer(self.allocated_capital, len(stocks))

        if caps is None:
            total_alloc = sum(s.allocation_pct for s in stocks)
            for stock in stocks:
                cls = classes.get(stock.ticker, AssetClass.EQUITY)
                normalized = (
                    stock.allocation_pct / total_alloc if total_alloc > 0 else 0.0
                )
                results.append(
                    self._open_long(
                        stock.ticker,
                        cls,
                        net_base * normalized,
                        fractionable=frac.get(stock.ticker, False),
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
                    ticker,
                    cls,
                    net_base * weights.get(ticker, 0.0),
                    fractionable=frac.get(ticker, False),
                )
            )
        return results

    def _open_long(
        self,
        ticker: str,
        cls: AssetClass,
        capital_for_stock: float,
        fractionable: bool = False,
    ) -> TradeResult:
        """Size ``capital_for_stock`` into a whole/fractional long and place the buy.

        ``fractionable`` reports whether the brokerage lists ``ticker`` as a
        fractionable equity; when ``True`` the equity is sized in fractional shares
        (skipping only sub-:data:`MIN_EQUITY_NOTIONAL_USD` allocations), otherwise it
        keeps the whole-share truncation. Crypto is always fractional.
        """
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
            elif fractionable:
                qty = round(capital_for_stock / price, EQUITY_QTY_PRECISION)
                if qty <= 0 or qty * price < MIN_EQUITY_NOTIONAL_USD:
                    return TradeResult(
                        ticker=ticker,
                        side="long",
                        shares=0,
                        price=price,
                        executed=False,
                        reason=(
                            f"Allocation ${capital_for_stock:.2f} below "
                            f"min notional ${MIN_EQUITY_NOTIONAL_USD:.2f}"
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
        unallocated_cash: float | None = None,
        fractionable: dict[str, bool] | None = None,
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

        Sizing is class- and fractionability-aware: crypto and equities whose
        ``fractionable`` flag is ``True`` use fractional deltas (skip when the
        delta's notional is below the asset's minimum tradable notional —
        :data:`MIN_CRYPTO_NOTIONAL_USD` / :data:`MIN_EQUITY_NOTIONAL_USD`), while
        non-fractionable (or unknown) equities use whole-share deltas (skip
        ``|delta| < 1``). ``fractionable`` maps a ticker to its brokerage
        fractionability; an absent ticker is treated as non-fractionable. When
        ``market_open`` is ``False``,
        equity tickers are recorded as not executed ("equity market closed") and
        no order is placed, while crypto tickers trade normally.

        When ``unallocated_cash`` is provided (the session's free cash), the run is
        skipped as a no-op once its intents are planned but before any order is
        submitted, iff the plan has **no sell intents** AND no deployable cash — the
        free cash in excess of the reserved buffer (``base - net_base``) is ``<= 0``.
        Such a plan can only buy but has nothing to fund the buys (most visibly the
        first rebalance right after a build, when the capital is already deployed and
        only the buffer remains). On skip, :attr:`skipped_noop` is set and the
        planned ``skips`` are returned without submitting anything. A plan with at
        least one sell, or with deployable cash, proceeds. Passing ``None`` (the
        default) disables the check and preserves the prior behaviour for callers
        that do not supply live cash.
        """
        self.skipped_noop = False
        classes = asset_classes or {}
        frac = fractionable or {}
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

        total_target_weight = sum(target_weight.values())

        base = self.allocated_capital if base_capital is None else base_capital
        tickers = sorted(set(current_positions) | set(target_weight))

        # Reserve a cash buffer before sizing so a fully invested target does not
        # deploy the whole value and then overdraw on fees / fill slippage. Each
        # candidate ticker yields at most one order, so ``len(tickers)``
        # upper-bounds the run's fees. The crypto-only budget already flows
        # through ``base``, so its base is reduced the same way.
        net_base = self._reserve_cash_buffer(base, len(tickers))

        # Phase 0: decide and size every ticker into an order intent (no
        # submission yet). Non-order outcomes — equity skipped while the market is
        # closed, a missing quote, or a sizing error — are recorded immediately so
        # they still appear in the returned results.
        skips: list[TradeResult] = []
        sell_intents: list[_OrderIntent] = []
        buy_intents: list[_OrderIntent] = []

        # Phase 0a: price every ticker once. An equity skipped while the market is
        # closed keeps its weight uninvested for this run (a transient condition
        # that heals on the next open-market run), so it is NOT redeployed
        # cross-asset. A ticker the broker cannot price is unexecutable; its weight
        # is redeployed across the executable targets in phase 0b.
        priced: dict[str, tuple[float, AssetClass, Position | None]] = {}
        closed_equity_weight = 0.0
        for ticker in tickers:
            cls = classes.get(ticker, AssetClass.EQUITY)
            pos = current_positions.get(ticker)
            weight = target_weight.get(ticker, 0.0)

            if not market_open and cls == AssetClass.EQUITY:
                closed_equity_weight += weight
                skips.append(
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
            except Exception as exc:  # noqa: BLE001 - one ticker must not abort the run
                logger.error("AI rebalance sizing failed for %s: %s", ticker, exc)
                skips.append(
                    TradeResult(
                        ticker=ticker,
                        side="long" if weight > 0 else "sell",
                        shares=0,
                        price=None,
                        executed=False,
                        reason=f"Order failed: {exc}",
                    )
                )
                continue

            if not price or price <= 0:
                skips.append(
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

            priced[ticker] = (price, cls, pos)

        # Phase 0b: redeploy the weight of unexecutable targets — unpriceable above,
        # or too small to fund the minimum tradable amount (one whole share for an
        # equity, the min crypto notional for a crypto) against ``net_base`` — across
        # the targets that CAN be executed, bounded by the reserved cash buffer
        # (sizing is against ``net_base``). Market-closed equity weight is held out
        # as cash for this run rather than redeployed cross-asset.
        deployable_ceiling = max(total_target_weight - closed_equity_weight, 0.0)
        priced_target_weights = {
            t: target_weight[t] for t in priced if target_weight.get(t, 0.0) > 0.0
        }
        # The minimum tradable amount is a dollar notional for anything sized
        # fractionally (crypto, or an equity the brokerage lists as fractionable)
        # and one whole share (its price) for a non-fractionable equity.
        min_notionals = {
            t: (
                MIN_CRYPTO_NOTIONAL_USD
                if priced[t][1] == AssetClass.CRYPTO
                else MIN_EQUITY_NOTIONAL_USD
                if frac.get(t, False)
                else priced[t][0]
            )
            for t in priced
        }
        final_weight, too_small = self._redeploy_target_weights(
            priced_target_weights, min_notionals, net_base, deployable_ceiling
        )

        # Guardrails clamp the *redeployed* vector so redeployment never breaches a
        # cap; weight that cannot be placed without breaching one stays cash.
        if caps is not None:
            final_weight = enforce_guardrails(final_weight, classes, caps)

        # Phase 0c: size every priced ticker against its redeployed weight. A target
        # the run wanted but could not fund (too small and not already held) is
        # recorded as not executed rather than dropped silently; a held position at a
        # removed target is exited by the delta model (a real sell), and a genuine
        # ``|delta| < 1`` adjustment of an at-target holding stays a non-surfaced
        # no-op.
        for ticker, (price, cls, pos) in priced.items():
            weight = final_weight.get(ticker, 0.0)
            if cls == AssetClass.CRYPTO:
                intent = self._plan_crypto(ticker, pos, weight, price, net_base)
            else:
                intent = self._plan_equity(
                    ticker,
                    pos,
                    weight,
                    price,
                    net_base,
                    fractionable=frac.get(ticker, False),
                )

            if intent is None:
                if ticker in too_small and pos is None:
                    skips.append(
                        TradeResult(
                            ticker=ticker,
                            side="long",
                            shares=0,
                            price=price,
                            executed=False,
                            reason="Allocation too small to fund the minimum tradable amount",
                        )
                    )
                continue
            if intent.side == "sell":
                sell_intents.append(intent)
            else:
                buy_intents.append(intent)

        # No-op skip: the plan can only buy (no sells) and there is no cash to
        # deploy beyond the reserved buffer, so submitting it would do nothing but
        # churn fees. Decided from the planned intents before any submission, so no
        # partial execution. ``reserve`` is the buffer already carved out of the
        # sizing base; deployable cash is free cash in excess of it.
        if unallocated_cash is not None and not sell_intents:
            reserve = base - net_base
            deployable_cash = unallocated_cash - reserve
            if deployable_cash <= 0.0:
                self.skipped_noop = True
                return skips

        # Phase 1: submit every sell first (with bounded retry on rejection).
        sell_results = [self._submit_intent(i) for i in sell_intents]

        results: list[TradeResult] = [*skips, *sell_results]

        # Phase 2: gate the buys on the sells reaching a terminal broker state,
        # then submit all buys at once. On fill-wait timeout, withhold the buys
        # (fail-safe) and record each as not executed; the executed sells stay.
        if buy_intents:
            if self._await_sell_fills(sell_results):
                results.extend(self._submit_intent(i) for i in buy_intents)
            else:
                logger.warning(
                    "AI rebalance: sells did not settle within %ss; withholding "
                    "%d buy order(s)",
                    settings.REBALANCE_SELL_FILL_TIMEOUT_SECONDS,
                    len(buy_intents),
                )
                results.extend(
                    TradeResult(
                        ticker=i.ticker,
                        side=i.side,
                        shares=0,
                        price=None,
                        executed=False,
                        reason="sells not yet filled",
                    )
                    for i in buy_intents
                )

        return results

    def _submit_intent(self, intent: _OrderIntent) -> TradeResult:
        """Submit one planned order, retrying a rejection up to the configured cap.

        Returns an executed :class:`TradeResult` once the broker accepts the order
        (any non-rejected status, including the async ``SUBMITTED`` whose fill is
        reconciled later). After exhausting the retry budget on a rejection — or on
        a broker order error — returns a not-executed result; a single failure
        never aborts the run.
        """
        attempts = max(1, settings.REBALANCE_ORDER_MAX_ATTEMPTS)
        last_exc: Exception | None = None
        rejected = False
        for attempt in range(1, attempts + 1):
            try:
                if intent.side == "sell":
                    order = self.broker.sell(
                        intent.ticker, intent.quantity, asset_class=intent.asset_class
                    )
                else:
                    order = self.broker.buy(
                        intent.ticker, intent.quantity, asset_class=intent.asset_class
                    )
            except Exception as exc:  # noqa: BLE001 - one order must not abort the run
                last_exc = exc
                logger.warning(
                    "AI rebalance %s %s attempt %d/%d failed: %s",
                    intent.side,
                    intent.ticker,
                    attempt,
                    attempts,
                    exc,
                )
                continue

            if order.status == OrderStatus.REJECTED:
                rejected = True
                logger.warning(
                    "AI rebalance %s %s rejected on attempt %d/%d",
                    intent.side,
                    intent.ticker,
                    attempt,
                    attempts,
                )
                continue

            fill_price = order.filled_price or intent.price
            logger.info(
                "AI rebalance: %s %s %s",
                intent.side,
                intent.quantity,
                intent.ticker,
            )
            return TradeResult(
                ticker=intent.ticker,
                side=intent.side,
                shares=intent.quantity,
                price=fill_price,
                executed=True,
                reason=intent.reason,
                order_id=order.order_id,
                order_status=order.status,
                filled_price=order.filled_price,
            )

        reason = (
            f"Order failed: {last_exc}"
            if last_exc is not None
            else f"Order rejected by broker after {attempts} attempt(s)"
        )
        return TradeResult(
            ticker=intent.ticker,
            side=intent.side,
            shares=0,
            price=None,
            executed=False,
            reason=reason,
            order_status=OrderStatus.REJECTED if rejected else OrderStatus.FILLED,
        )

    def _await_sell_fills(self, sell_results: list[TradeResult]) -> bool:
        """Poll the broker until every submitted sell is terminal, or timeout.

        Only executed sells carrying an ``order_id`` and a non-terminal status are
        waited on; a sell with no order id or an already-terminal status (the
        immediate-fill stub returns ``FILLED``) contributes nothing to wait on, so
        the gate opens at once. Returns ``True`` when all sells settled within the
        configured timeout, ``False`` on timeout.
        """
        pending = [
            r.order_id
            for r in sell_results
            if r.executed
            and r.order_id
            and r.order_status not in _TERMINAL_ORDER_STATUSES
        ]
        if not pending:
            return True  # nothing to wait on => ready

        deadline = time.monotonic() + settings.REBALANCE_SELL_FILL_TIMEOUT_SECONDS
        poll = max(0.0, settings.REBALANCE_SELL_FILL_POLL_SECONDS)
        while True:
            still: list[str] = []
            for order_id in pending:
                order = self.broker.get_order(order_id)
                if order is None or order.is_complete:
                    continue  # unknown or terminal => settled
                still.append(order_id)
            if not still:
                return True
            if time.monotonic() >= deadline:
                return False
            pending = still
            time.sleep(poll)

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
                    # Liquidate the full held quantity. Rounding to the equity
                    # precision sells a fractional holding whole and is identical
                    # to int-truncation for a whole-share position, so this is
                    # correct regardless of the asset's fractionability.
                    qty = round(abs(pos.quantity), EQUITY_QTY_PRECISION)
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

    def _plan_equity(
        self,
        ticker: str,
        pos: Position | None,
        weight: float,
        price: float,
        base_capital: float,
        fractionable: bool = False,
    ) -> _OrderIntent | None:
        """Plan a delta trade for an equity.

        When ``fractionable`` is ``True`` the equity is sized in fractional shares
        exactly like crypto — the delta is rounded to :data:`EQUITY_QTY_PRECISION`
        and skipped only when its notional is below :data:`MIN_EQUITY_NOTIONAL_USD`.
        Otherwise it uses whole-share deltas (skip ``|delta| < 1``).

        Decides the side and sizes the order but does not submit it; returns
        ``None`` for a no-op. Submission happens later in the sells-before-buys
        phase via :meth:`_submit_intent`.
        """
        if fractionable:
            return self._plan_fractional(
                ticker,
                pos,
                weight,
                price,
                base_capital,
                asset_class=AssetClass.EQUITY,
                precision=EQUITY_QTY_PRECISION,
                min_notional=MIN_EQUITY_NOTIONAL_USD,
                unit="shares",
            )

        current_shares = int(pos.quantity) if pos else 0
        target_shares = int(base_capital * weight / price) if weight > 0 else 0
        delta = target_shares - current_shares

        if delta >= 1:
            return _OrderIntent(
                ticker=ticker,
                asset_class=AssetClass.EQUITY,
                side="long",
                quantity=delta,
                price=price,
                reason=f"Bought {delta} shares toward target",
            )
        if delta <= -1:
            qty = min(-delta, current_shares)
            if qty < 1:
                return None
            reason = (
                f"Sold {qty} shares (exit)"
                if target_shares == 0
                else f"Sold {qty} shares toward target"
            )
            return _OrderIntent(
                ticker=ticker,
                asset_class=AssetClass.EQUITY,
                side="sell",
                quantity=qty,
                price=price,
                reason=reason,
            )
        # |delta| < 1: no-op, no order planned.
        return None

    def _plan_crypto(
        self,
        ticker: str,
        pos: Position | None,
        weight: float,
        price: float,
        base_capital: float,
    ) -> _OrderIntent | None:
        """Plan a fractional delta trade for a crypto (skip sub-min-notional deltas).

        Decides the side and sizes the order but does not submit it; returns
        ``None`` when the delta's notional is below the minimum. Submission happens
        later in the sells-before-buys phase via :meth:`_submit_intent`.
        """
        return self._plan_fractional(
            ticker,
            pos,
            weight,
            price,
            base_capital,
            asset_class=AssetClass.CRYPTO,
            precision=CRYPTO_QTY_PRECISION,
            min_notional=MIN_CRYPTO_NOTIONAL_USD,
            unit="units",
        )

    def _plan_fractional(
        self,
        ticker: str,
        pos: Position | None,
        weight: float,
        price: float,
        base_capital: float,
        *,
        asset_class: AssetClass,
        precision: int,
        min_notional: float,
        unit: str,
    ) -> _OrderIntent | None:
        """Plan a fractional-quantity delta trade for a fractionable asset.

        Shared by crypto and fractionable-equity sizing. The target quantity is
        ``base_capital * weight / price`` rounded to ``precision`` decimal places,
        the delta is the signed difference from the held quantity, and a delta whose
        notional is below ``min_notional`` is a no-op (returns ``None``). ``unit``
        is the human word used in the trade reason ("units" / "shares").
        """
        current = pos.quantity if pos else 0.0
        target = round(base_capital * weight / price, precision) if weight > 0 else 0.0
        delta = round(target - current, precision)

        if abs(delta) * price < min_notional:
            # Below min notional (covers the near-zero delta no-op case too).
            return None

        if delta > 0:
            return _OrderIntent(
                ticker=ticker,
                asset_class=asset_class,
                side="long",
                quantity=delta,
                price=price,
                reason=f"Bought {delta} {unit} toward target",
            )
        # delta < 0: sell the shortfall, capped at the held quantity (exit sells
        # the full current float when weight is 0).
        qty = round(min(-delta, current), precision)
        if qty <= 0:
            return None
        reason = (
            f"Sold {qty} {unit} (exit)"
            if target == 0
            else f"Sold {qty} {unit} toward target"
        )
        return _OrderIntent(
            ticker=ticker,
            asset_class=asset_class,
            side="sell",
            quantity=qty,
            price=price,
            reason=reason,
        )
