"""Unit tests for the pure eligibility evaluator."""

from __future__ import annotations

from cadence.assets.category import AssetCategory
from cadence.assets.constants import (
    MIN_AVG_DAILY_TURNOVER_USD,
    MIN_CRYPTO_AVG_DAILY_TURNOVER_USD,
    MIN_CRYPTO_HISTORY_YEARS,
    MIN_CRYPTO_MARKET_CAP_USD,
    MIN_HISTORY_YEARS,
    MIN_MARKET_CAP_USD,
    MIN_PRICE_USD,
)
from cadence.assets.evaluation import AssetMetrics, evaluate


def _passing_metrics() -> AssetMetrics:
    return AssetMetrics(
        price_usd=10.0,
        avg_daily_turnover_usd=3_000_000.0,
        market_cap_usd=2_000_000_000.0,
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
        price_usd=1.0,
        avg_daily_turnover_usd=3_000_000.0,
        market_cap_usd=2_000_000_000.0,
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
        price_usd=10.0,
        avg_daily_turnover_usd=1_000.0,
        market_cap_usd=2_000_000_000.0,
        history_years=10.0,
    )
    result = evaluate(metrics)
    assert result.is_eligible is False
    assert _results_by_name(metrics)["avg_daily_turnover"] is False


def test_market_cap_single_fail() -> None:
    metrics = AssetMetrics(
        price_usd=10.0,
        avg_daily_turnover_usd=3_000_000.0,
        market_cap_usd=5.0,
        history_years=10.0,
    )
    result = evaluate(metrics)
    assert result.is_eligible is False
    assert _results_by_name(metrics)["market_cap"] is False


def test_history_single_fail() -> None:
    metrics = AssetMetrics(
        price_usd=10.0,
        avg_daily_turnover_usd=3_000_000.0,
        market_cap_usd=2_000_000_000.0,
        history_years=1.0,
    )
    result = evaluate(metrics)
    assert result.is_eligible is False
    assert _results_by_name(metrics)["history"] is False


def test_none_metric_fails_its_criterion() -> None:
    metrics = AssetMetrics(
        price_usd=None,
        avg_daily_turnover_usd=3_000_000.0,
        market_cap_usd=2_000_000_000.0,
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
        price_usd=float(MIN_PRICE_USD),  # exactly 5 -> fails (not > 5)
        avg_daily_turnover_usd=float(MIN_AVG_DAILY_TURNOVER_USD),  # == -> passes
        market_cap_usd=float(MIN_MARKET_CAP_USD),  # exactly 1e9 -> fails
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
    assert thresholds["price"] == float(MIN_PRICE_USD)
    assert thresholds["avg_daily_turnover"] == float(MIN_AVG_DAILY_TURNOVER_USD)
    assert thresholds["market_cap"] == float(MIN_MARKET_CAP_USD)
    assert thresholds["history"] == float(MIN_HISTORY_YEARS)


# --------------------------------------------------------------------------- #
# Crypto profile: no price criterion, shorter history, raised liquidity/cap.
# --------------------------------------------------------------------------- #


def _passing_crypto_metrics() -> AssetMetrics:
    return AssetMetrics(
        price_usd=None,  # ignored for crypto
        avg_daily_turnover_usd=float(MIN_CRYPTO_AVG_DAILY_TURNOVER_USD) + 1,
        market_cap_usd=float(MIN_CRYPTO_MARKET_CAP_USD) + 1,
        history_years=float(MIN_CRYPTO_HISTORY_YEARS) + 1,
    )


def test_crypto_profile_has_no_price_criterion() -> None:
    result = evaluate(_passing_crypto_metrics(), AssetCategory.CRYPTO)
    assert result.is_eligible is True
    assert {c.name for c in result.criteria} == {
        "avg_daily_turnover",
        "market_cap",
        "history",
    }


def test_crypto_ignores_price_even_when_absurdly_low() -> None:
    # A per-unit price well under the $5 stock floor is irrelevant for crypto.
    metrics = AssetMetrics(
        price_usd=0.0001,
        avg_daily_turnover_usd=float(MIN_CRYPTO_AVG_DAILY_TURNOVER_USD) + 1,
        market_cap_usd=float(MIN_CRYPTO_MARKET_CAP_USD) + 1,
        history_years=float(MIN_CRYPTO_HISTORY_YEARS) + 1,
    )
    result = evaluate(metrics, AssetCategory.CRYPTO)
    assert result.is_eligible is True
    assert all(c.name != "price" for c in result.criteria)


def test_crypto_uses_raised_thresholds() -> None:
    result = evaluate(_passing_crypto_metrics(), AssetCategory.CRYPTO)
    thresholds = {c.name: c.threshold for c in result.criteria}
    assert thresholds["avg_daily_turnover"] == float(MIN_CRYPTO_AVG_DAILY_TURNOVER_USD)
    assert thresholds["market_cap"] == float(MIN_CRYPTO_MARKET_CAP_USD)
    assert thresholds["history"] == float(MIN_CRYPTO_HISTORY_YEARS)


def test_crypto_stricter_than_stock_on_shared_criteria() -> None:
    # Metrics that clear the stock floors but not the (higher) crypto floors:
    # $1.5B cap (> $1B, < $2B) and $3M turnover (> $2M, < $10M).
    metrics = AssetMetrics(
        price_usd=None,
        avg_daily_turnover_usd=3_000_000.0,
        market_cap_usd=1_500_000_000.0,
        history_years=2.0,
    )
    # Passes as a stock...
    assert evaluate(metrics, AssetCategory.STOCK).is_eligible is False  # price None
    # ...but the shared criteria specifically fail under crypto's higher floors.
    crypto = evaluate(metrics, AssetCategory.CRYPTO)
    passed = {c.name: c.passed for c in crypto.criteria}
    assert passed["avg_daily_turnover"] is False
    assert passed["market_cap"] is False
    assert passed["history"] is True  # 2 years > 1-year crypto floor
    assert crypto.is_eligible is False


def test_crypto_history_floor_is_one_year() -> None:
    # 2-year history fails the 5-year stock floor but passes the 1-year crypto one.
    metrics = AssetMetrics(
        price_usd=None,
        avg_daily_turnover_usd=float(MIN_CRYPTO_AVG_DAILY_TURNOVER_USD) + 1,
        market_cap_usd=float(MIN_CRYPTO_MARKET_CAP_USD) + 1,
        history_years=2.0,
    )
    result = evaluate(metrics, AssetCategory.CRYPTO)
    history = next(c for c in result.criteria if c.name == "history")
    assert history.passed is True
    assert result.is_eligible is True


def test_default_category_is_stock_profile() -> None:
    # Calling without a category evaluates the stock profile (four criteria).
    result = evaluate(_passing_metrics())
    assert {c.name for c in result.criteria} == {
        "price",
        "avg_daily_turnover",
        "market_cap",
        "history",
    }
