"""Unit tests for the pure sizing + shared-pool allocation helpers.

These cover task §2: Wilder ATR, per-position sizing bounded by every constraint,
and the budget-ceiling allocation across a basket. All are pure (no I/O / ORM).
"""

from __future__ import annotations

from datetime import UTC, datetime
from math import floor

import pytest

from cadence.strategy_bots.constants import SizingMethod
from cadence.strategy_bots.sizing import (
    EntryCandidate,
    atr,
    plan_entries,
    size_position,
)
from cadence.strategy_bots.strategy import Bar

_NOW = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)


def _bar(high: float, low: float, close: float) -> Bar:
    return Bar(
        timestamp=_NOW, open=close, high=high, low=low, close=close, volume=1.0
    )


# ATR ---------------------------------------------------------------------
def test_atr_matches_hand_computed_mean_true_range() -> None:
    # Four bars → three true ranges over period=3. Prev close drives TR[i].
    bars = [
        _bar(high=11.0, low=9.0, close=10.0),  # seeds prev_close only
        _bar(high=12.0, low=10.0, close=11.0),  # TR = max(2, |12-10|, |10-10|) = 2
        _bar(high=13.0, low=11.5, close=12.0),  # TR = max(1.5, |13-11|, |11.5-11|) = 2
        _bar(high=12.5, low=11.0, close=11.5),  # TR = max(1.5, |12.5-12|, |11-12|) = 1.5
    ]
    # Mean of [2.0, 2.0, 1.5] = 1.8333...
    assert atr(bars, 3) == pytest.approx((2.0 + 2.0 + 1.5) / 3)


def test_atr_insufficient_history_returns_none() -> None:
    bars = [_bar(11.0, 9.0, 10.0), _bar(12.0, 10.0, 11.0)]
    # Needs period + 1 = 4 bars for period 3.
    assert atr(bars, 3) is None


def test_atr_zero_range_returns_none() -> None:
    flat = [_bar(10.0, 10.0, 10.0) for _ in range(5)]
    assert atr(flat, 3) is None


# size_position -----------------------------------------------------------
def _size(**overrides: object) -> int:
    kwargs: dict[str, object] = {
        "method": SizingMethod.ATR_RISK,
        "price": 100.0,
        "atr_value": 2.0,
        "budget": 100_000.0,
        "available_cash": 100_000.0,
        "risk_pct": 0.01,
        "atr_k": 2.0,
        "max_position_pct": 0.25,
        "cash_buffer_pct": 0.0,
    }
    kwargs.update(overrides)
    return size_position(**kwargs)  # type: ignore[arg-type]


def test_atr_sizing_targets_equal_dollar_risk() -> None:
    # risk$ = 100k * 0.01 = 1000; per-share risk = 2 * ATR.
    low_atr = _size(atr_value=2.0)  # floor(1000 / 4) = 250, capped by per-name/cash
    high_atr = _size(atr_value=5.0)  # floor(1000 / 10) = 100
    # Higher ATR → fewer shares at the same price (equal dollar risk).
    assert high_atr < low_atr
    assert high_atr == 100


def test_per_name_cap_binds_size() -> None:
    # Loose ATR target but a tight per-name cap: 5% of 100k / 100 = 50 shares.
    shares = _size(atr_value=0.01, max_position_pct=0.05)
    assert shares == floor((100_000.0 * 0.05) / 100.0)


def test_cash_bound_binds_size() -> None:
    # Only $600 spendable → 6 shares at $100 despite a larger ATR target.
    shares = _size(atr_value=0.01, available_cash=600.0)
    assert shares == 6


def test_below_one_share_returns_zero() -> None:
    assert _size(available_cash=50.0) == 0  # can't afford one $100 share


def test_atr_unavailable_skips_atr_sizing() -> None:
    assert _size(atr_value=None) == 0


def test_all_in_fills_affordable_shares_within_cap() -> None:
    # ALL_IN ignores ATR: floor(available / price) within the per-name cap.
    shares = size_position(
        method=SizingMethod.ALL_IN,
        price=100.0,
        atr_value=None,
        budget=100_000.0,
        available_cash=1_000.0,
        risk_pct=0.01,
        atr_k=2.0,
        max_position_pct=1.0,
        cash_buffer_pct=0.0,
    )
    assert shares == 10


# plan_entries (shared-pool budget ceiling) -------------------------------
def _candidate(ticker: str, price: float, atr_value: float = 1.0) -> EntryCandidate:
    return EntryCandidate(
        ticker=ticker,
        symbol=ticker,
        asset_id=hash(ticker) % 1000,
        price=price,
        atr_value=atr_value,
    )


def test_budget_ceiling_never_exceeded_when_many_signal() -> None:
    # Five all-in candidates, each cheap enough to consume lots of cash, but the
    # shared pool is only $10k — funded cost must never exceed available cash.
    candidates = [_candidate(f"SYM{i}", price=100.0) for i in range(5)]
    planned = plan_entries(
        candidates,
        budget=10_000.0,
        available_cash=10_000.0,
        open_positions=0,
        max_positions=10,
        sizing_method=SizingMethod.ALL_IN,
        risk_pct=0.01,
        atr_k=2.0,
        max_position_pct=1.0,
        cash_buffer_pct=0.0,
    )
    assert sum(p.cost for p in planned) <= 10_000.0


def test_max_positions_caps_funded_entries() -> None:
    candidates = [_candidate(f"SYM{i}", price=100.0) for i in range(5)]
    planned = plan_entries(
        candidates,
        budget=100_000.0,
        available_cash=100_000.0,
        open_positions=1,  # one slot already used
        max_positions=3,  # only 2 slots remain
        sizing_method=SizingMethod.ALL_IN,
        risk_pct=0.01,
        atr_k=2.0,
        max_position_pct=0.10,
        cash_buffer_pct=0.0,
    )
    assert len(planned) == 2


def test_entries_sized_against_remaining_cash_in_order() -> None:
    # Two names, per-name cap 60% of a 1000 budget = 600 each. The first consumes
    # 600, leaving 400 — so the second is bounded by cash, not its own cap.
    first, second = _candidate("AAA", 100.0), _candidate("BBB", 100.0)
    planned = plan_entries(
        [first, second],
        budget=1_000.0,
        available_cash=1_000.0,
        open_positions=0,
        max_positions=10,
        sizing_method=SizingMethod.ALL_IN,
        risk_pct=0.01,
        atr_k=2.0,
        max_position_pct=0.60,
        cash_buffer_pct=0.0,
    )
    assert [p.shares for p in planned] == [6, 4]
    assert sum(p.cost for p in planned) <= 1_000.0
