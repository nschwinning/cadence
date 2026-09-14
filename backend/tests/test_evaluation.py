"""Unit tests for the pure eligibility evaluator."""

from __future__ import annotations

from cadence.assets.constants import (
    MIN_AVG_DAILY_TURNOVER_EUR,
    MIN_HISTORY_YEARS,
    MIN_MARKET_CAP_EUR,
    MIN_PRICE_EUR,
)
from cadence.assets.evaluation import AssetMetrics, evaluate


def _passing_metrics() -> AssetMetrics:
    return AssetMetrics(
        price_eur=10.0,
        avg_daily_turnover_eur=3_000_000.0,
        market_cap_eur=2_000_000_000.0,
        history_years=10.0,
    )


def _results_by_name(metrics: AssetMetrics) -> dict[str, bool]:
    result = evaluate(metrics)
    return {c.name: c.passed for c in result.criteria}


def test_all_criteria_pass() -> None:
    result = evaluate(_passing_metrics())
    assert result.is_eligible is True
    assert {c.name for c in result.criteria} == {
        "price",
        "avg_daily_turnover",
        "market_cap",
        "history",
    }
    assert all(c.passed for c in result.criteria)


def test_price_single_fail() -> None:
    metrics = AssetMetrics(
        price_eur=1.0,
        avg_daily_turnover_eur=3_000_000.0,
        market_cap_eur=2_000_000_000.0,
        history_years=10.0,
    )
    result = evaluate(metrics)
    assert result.is_eligible is False
    passed = _results_by_name(metrics)
    assert passed["price"] is False
    assert passed["avg_daily_turnover"] is True
    assert passed["market_cap"] is True
    assert passed["history"] is True


def test_turnover_single_fail() -> None:
    metrics = AssetMetrics(
        price_eur=10.0,
        avg_daily_turnover_eur=1_000.0,
        market_cap_eur=2_000_000_000.0,
        history_years=10.0,
    )
    result = evaluate(metrics)
    assert result.is_eligible is False
    assert _results_by_name(metrics)["avg_daily_turnover"] is False


def test_market_cap_single_fail() -> None:
    metrics = AssetMetrics(
        price_eur=10.0,
        avg_daily_turnover_eur=3_000_000.0,
        market_cap_eur=5.0,
        history_years=10.0,
    )
    result = evaluate(metrics)
    assert result.is_eligible is False
    assert _results_by_name(metrics)["market_cap"] is False


def test_history_single_fail() -> None:
    metrics = AssetMetrics(
        price_eur=10.0,
        avg_daily_turnover_eur=3_000_000.0,
        market_cap_eur=2_000_000_000.0,
        history_years=1.0,
    )
    result = evaluate(metrics)
    assert result.is_eligible is False
    assert _results_by_name(metrics)["history"] is False


def test_none_metric_fails_its_criterion() -> None:
    metrics = AssetMetrics(
        price_eur=None,
        avg_daily_turnover_eur=3_000_000.0,
        market_cap_eur=2_000_000_000.0,
        history_years=10.0,
    )
    result = evaluate(metrics)
    assert result.is_eligible is False
    price = next(c for c in result.criteria if c.name == "price")
    assert price.passed is False
    assert price.value is None


def test_boundary_values() -> None:
    # price uses strict >, turnover uses >=, market_cap uses strict >,
    # history uses >=.
    metrics = AssetMetrics(
        price_eur=float(MIN_PRICE_EUR),  # exactly 5 -> fails (not > 5)
        avg_daily_turnover_eur=float(MIN_AVG_DAILY_TURNOVER_EUR),  # == -> passes
        market_cap_eur=float(MIN_MARKET_CAP_EUR),  # exactly 1e9 -> fails
        history_years=float(MIN_HISTORY_YEARS),  # == 5 -> passes
    )
    passed = _results_by_name(metrics)
    assert passed["price"] is False
    assert passed["avg_daily_turnover"] is True
    assert passed["market_cap"] is False
    assert passed["history"] is True

    # thresholds are reported on each criterion
    result = evaluate(metrics)
    thresholds = {c.name: c.threshold for c in result.criteria}
    assert thresholds["price"] == float(MIN_PRICE_EUR)
    assert thresholds["avg_daily_turnover"] == float(MIN_AVG_DAILY_TURNOVER_EUR)
    assert thresholds["market_cap"] == float(MIN_MARKET_CAP_EUR)
    assert thresholds["history"] == float(MIN_HISTORY_YEARS)
