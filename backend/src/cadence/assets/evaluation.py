"""Pure EUR-based eligibility evaluation.

No I/O here: :func:`evaluate` is a pure function of the derived metrics, making
it trivially unit-testable across pass/fail combinations. Criteria are uniform
across all asset categories in v1.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cadence.assets.constants import (
    MIN_AVG_DAILY_TURNOVER_EUR,
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


def evaluate(metrics: AssetMetrics) -> EvaluationResult:
    """Evaluate ``metrics`` against Cadence's four EUR-based criteria.

    An asset is eligible only when every criterion passes. A missing (``None``)
    metric fails its criterion.
    """
    criteria = [
        _criterion(
            CRITERION_PRICE,
            metrics.price_eur,
            MIN_PRICE_EUR,
            lambda value: value > MIN_PRICE_EUR,
        ),
        _criterion(
            CRITERION_AVG_DAILY_TURNOVER,
            metrics.avg_daily_turnover_eur,
            MIN_AVG_DAILY_TURNOVER_EUR,
            lambda value: value >= MIN_AVG_DAILY_TURNOVER_EUR,
        ),
        _criterion(
            CRITERION_MARKET_CAP,
            metrics.market_cap_eur,
            MIN_MARKET_CAP_EUR,
            lambda value: value > MIN_MARKET_CAP_EUR,
        ),
        _criterion(
            CRITERION_HISTORY,
            metrics.history_years,
            MIN_HISTORY_YEARS,
            lambda value: value >= MIN_HISTORY_YEARS,
        ),
    ]
    return EvaluationResult(
        is_eligible=all(result.passed for result in criteria),
        criteria=criteria,
    )


def _criterion(
    name: str,
    value: float | None,
    threshold: float,
    predicate: Callable[[float], bool],
) -> CriterionResult:
    passed = value is not None and predicate(value)
    return CriterionResult(
        name=name, passed=passed, value=value, threshold=float(threshold)
    )
