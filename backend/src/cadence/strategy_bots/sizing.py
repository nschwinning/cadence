"""Pure position-sizing and shared-pool allocation helpers.

These are deliberately free of I/O and ORM state so the money math — ATR, per-position
sizing, and the budget-ceiling allocation across a basket — is unit-testable in
isolation and deterministic. The tick runner (:mod:`.service`) fetches bars and
positions, then drives these helpers; the budget ceiling (``Σ open-position cost ≤
budget``) is enforced here by sizing every entry against *remaining* cash.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import floor

from cadence.strategy_bots.constants import SizingMethod
from cadence.strategy_bots.strategy import Bar


def atr(bars: Sequence[Bar], period: int) -> float | None:
    """Average True Range over the final ``period`` bars (Wilder's True Range mean).

    True Range of each bar is ``max(high-low, |high-prev_close|, |low-prev_close|)``;
    the ATR is the mean of the last ``period`` true ranges. Returns ``None`` when there
    is insufficient history (fewer than ``period + 1`` bars, since the first TR needs a
    previous close) or when the computed ATR is not strictly positive — both cases mean
    ATR-based sizing cannot run for that symbol this tick.
    """
    if period < 1 or len(bars) < period + 1:
        return None
    true_ranges: list[float] = []
    for i in range(1, len(bars)):
        high = bars[i].high
        low = bars[i].low
        prev_close = bars[i - 1].close
        true_ranges.append(
            max(high - low, abs(high - prev_close), abs(low - prev_close))
        )
    window = true_ranges[-period:]
    if len(window) < period:
        return None
    value = sum(window) / len(window)
    return value if value > 0 else None


def size_position(
    *,
    method: SizingMethod,
    price: float,
    atr_value: float | None,
    budget: float,
    available_cash: float,
    risk_pct: float,
    atr_k: float,
    max_position_pct: float,
    cash_buffer_pct: float,
) -> int:
    """Whole-share size for one new long position, bounded by every constraint.

    ``ATR_RISK`` targets ``floor((budget * risk_pct) / (atr_k * ATR))`` shares — an
    equal dollar risk per name, so a higher-ATR symbol gets fewer shares at the same
    price. ``ALL_IN`` targets the greatest number of shares affordable from spendable
    cash. Both are then capped by the per-name notional (``max_position_pct`` of the
    budget) and by spendable cash (``available_cash`` less the ``cash_buffer_pct``
    cushion against the budget). Returns ``0`` — no trade — when fewer than one share
    is affordable, the price is non-positive, or ATR sizing has no usable ATR.
    """
    if price <= 0:
        return 0
    spendable = available_cash - budget * cash_buffer_pct
    if spendable < price:
        return 0

    per_name_cap_shares = floor((budget * max_position_pct) / price)
    cash_cap_shares = floor(spendable / price)

    if method is SizingMethod.ATR_RISK:
        if atr_value is None or atr_value <= 0:
            return 0
        per_share_risk = atr_k * atr_value
        if per_share_risk <= 0:
            return 0
        target = floor((budget * risk_pct) / per_share_risk)
    else:  # ALL_IN
        target = cash_cap_shares

    target = min(target, per_name_cap_shares, cash_cap_shares)
    return target if target >= 1 else 0


@dataclass(frozen=True)
class EntryCandidate:
    """A symbol signalling entry, with the inputs needed to size it."""

    #: Canonical ticker — candidates are funded in ascending-ticker order.
    ticker: str
    #: Broker/market-data symbol for execution.
    symbol: str
    #: Universe asset id (to create the position row).
    asset_id: int
    #: Latest close used for sizing and the notional cost.
    price: float
    #: ATR for the symbol this tick, or ``None`` when unavailable.
    atr_value: float | None


@dataclass(frozen=True)
class PlannedEntry:
    """A funded entry: how many shares to buy for a candidate and at what cost."""

    candidate: EntryCandidate
    shares: int
    cost: float


def plan_entries(
    candidates: Sequence[EntryCandidate],
    *,
    budget: float,
    available_cash: float,
    open_positions: int,
    max_positions: int,
    sizing_method: SizingMethod,
    risk_pct: float,
    atr_k: float,
    max_position_pct: float,
    cash_buffer_pct: float,
) -> list[PlannedEntry]:
    """Fund entries in order while they fit remaining cash and the position limit.

    ``candidates`` must already be in the deterministic (ascending-ticker) order the
    tick runner wants. Each entry is sized against the *remaining* cash after the ones
    already funded this tick, so the sum of funded cost can never exceed available cash
    (and thus never the budget). Entries that size to zero shares are skipped; funding
    stops once ``max_positions`` open slots are filled.
    """
    remaining_cash = available_cash
    slots = max_positions - open_positions
    planned: list[PlannedEntry] = []
    for candidate in candidates:
        if slots <= 0:
            break
        shares = size_position(
            method=sizing_method,
            price=candidate.price,
            atr_value=candidate.atr_value,
            budget=budget,
            available_cash=remaining_cash,
            risk_pct=risk_pct,
            atr_k=atr_k,
            max_position_pct=max_position_pct,
            cash_buffer_pct=cash_buffer_pct,
        )
        if shares < 1:
            continue
        cost = shares * candidate.price
        planned.append(PlannedEntry(candidate=candidate, shares=shares, cost=cost))
        remaining_cash -= cost
        slots -= 1
    return planned
