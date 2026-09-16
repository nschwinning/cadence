"""Pure EUR-based eligibility evaluation.

No I/O here: :func:`evaluate` is a pure function of the derived metrics and the
asset's category, making it trivially unit-testable across pass/fail
combinations.

Criteria are category-specific. Equities are evaluated against four criteria
(price, turnover, market cap, history). Crypto uses a different profile: per-unit
price is meaningless for crypto (it depends on token supply), so it is dropped;
history is shorter (a young asset class); and the market-cap/liquidity floors are
raised. The concrete thresholds live in ``constants.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cadence.assets.category import AssetCategory
from cadence.assets.constants import (
    MIN_AVG_DAILY_TURNOVER_EUR,
    MIN_CRYPTO_AVG_DAILY_TURNOVER_EUR,
    MIN_CRYPTO_HISTORY_YEARS,
    MIN_CRYPTO_MARKET_CAP_EUR,
    MIN_HISTORY_YEARS,
    MIN_MARKET_CAP_EUR,
    MIN_PRICE_EUR,
)

# Criterion names are part of the public API contract (frontend depends on them).
CRITERION_PRICE = "price"
CRITERION_AVG_DAILY_TURNOVER = "avg_daily_turnover"
CRITERION_MARKET_CAP = "market_cap"
CRITERION_HISTORY = "history"


@dataclass(frozen=True)
class AssetMetrics:
    """EUR-normalized metrics fed into the evaluator."""

    price_eur: float | None
    avg_daily_turnover_eur: float | None
    market_cap_eur: float | None
    history_years: float | None


@dataclass(frozen=True)
class CriterionResult:
    """Outcome of a single eligibility criterion."""

    name: str
    passed: bool
    value: float | None
    threshold: float


@dataclass(frozen=True)
class EvaluationResult:
    """Overall eligibility plus the per-criterion breakdown."""

    is_eligible: bool
    criteria: list[CriterionResult]


# Comparison operators. Price/market-cap use a strict ``>``; turnover/history use
# ``>=`` (a metric exactly at the floor still qualifies).
def _gt(value: float, threshold: float) -> bool:
    return value > threshold


def _gte(value: float, threshold: float) -> bool:
    return value >= threshold


@dataclass(frozen=True)
class _CriterionSpec:
    """A single criterion in a profile: which metric, its floor, and the test."""

    name: str
    metric: Callable[[AssetMetrics], float | None]
    threshold: float
    compare: Callable[[float, float], bool]


# Equity profile: all four criteria. Also the default for any non-crypto category.
_STOCK_CRITERIA: tuple[_CriterionSpec, ...] = (
    _CriterionSpec(CRITERION_PRICE, lambda m: m.price_eur, float(MIN_PRICE_EUR), _gt),
    _CriterionSpec(
        CRITERION_AVG_DAILY_TURNOVER,
        lambda m: m.avg_daily_turnover_eur,
        float(MIN_AVG_DAILY_TURNOVER_EUR),
        _gte,
    ),
    _CriterionSpec(
        CRITERION_MARKET_CAP,
        lambda m: m.market_cap_eur,
        float(MIN_MARKET_CAP_EUR),
        _gt,
    ),
    _CriterionSpec(
        CRITERION_HISTORY,
        lambda m: m.history_years,
        float(MIN_HISTORY_YEARS),
        _gte,
    ),
)

# Crypto profile: no per-unit price criterion; shorter history; raised
# liquidity/market-cap floors.
_CRYPTO_CRITERIA: tuple[_CriterionSpec, ...] = (
    _CriterionSpec(
        CRITERION_AVG_DAILY_TURNOVER,
        lambda m: m.avg_daily_turnover_eur,
        float(MIN_CRYPTO_AVG_DAILY_TURNOVER_EUR),
        _gte,
    ),
    _CriterionSpec(
        CRITERION_MARKET_CAP,
        lambda m: m.market_cap_eur,
        float(MIN_CRYPTO_MARKET_CAP_EUR),
        _gt,
    ),
    _CriterionSpec(
        CRITERION_HISTORY,
        lambda m: m.history_years,
        float(MIN_CRYPTO_HISTORY_YEARS),
        _gte,
    ),
)

# Category -> criteria profile. Categories absent here use the stock profile.
_CRITERIA_BY_CATEGORY: dict[AssetCategory, tuple[_CriterionSpec, ...]] = {
    AssetCategory.CRYPTO: _CRYPTO_CRITERIA,
}


def evaluate(
    metrics: AssetMetrics, category: AssetCategory = AssetCategory.STOCK
) -> EvaluationResult:
    """Evaluate ``metrics`` against the criteria profile for ``category``.

    Equities are scored against four criteria; crypto uses a distinct profile
    (no price criterion, shorter history, higher liquidity/market-cap floors).
    An asset is eligible only when every criterion in its profile passes. A
    missing (``None``) metric fails its criterion.
    """
    specs = _CRITERIA_BY_CATEGORY.get(category, _STOCK_CRITERIA)
    criteria = [
        _criterion(spec.name, spec.metric(metrics), spec.threshold, spec.compare) for spec in specs
    ]
    return EvaluationResult(
        is_eligible=all(result.passed for result in criteria),
        criteria=criteria,
    )


def _criterion(
    name: str,
    value: float | None,
    threshold: float,
    compare: Callable[[float, float], bool],
) -> CriterionResult:
    passed = value is not None and compare(value, threshold)
    return CriterionResult(name=name, passed=passed, value=value, threshold=float(threshold))
