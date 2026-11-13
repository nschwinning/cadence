"""The Bayesian Trend Predictor strategy — a long-only, three-regime Bayesian classifier.

Ported from the course "Algo 33 Bayesian Trend Predictor". Each bar's return
Δ = (close − previous close) ÷ previous close is scored under three regimes with a normal
likelihood: **UP** (mean +``drift``, σ ``trend_sigma``), **FLAT** (mean 0, σ ``flat_sigma``)
and **DOWN** (mean −``drift``, σ ``trend_sigma``). Bayes' rule updates the regime
probabilities return by return, each posterior becoming the next prior.

While flat the bot enters long when UP is the most likely regime with probability at least
``threshold`` (the course's LONG signal); while holding it exits when DOWN is the most likely
regime at that probability (the course's SHORT signal, used as the long exit). The course only
prints signals, so it has no take-profit, stop-loss or drawdown stop of its own.

Deviations from the course: it carries the posterior for its whole run; Cadence is stateless,
so the posterior is rebuilt each tick from equal priors over the latest ``replay_bars``
returns. The course rounds prices to whole rupees before computing Δ — dropped, since on a
low-priced stock every move would round to a huge return. The update runs in log space, so an
extreme return that underflows every likelihood keeps its direction instead of resetting the
probabilities to uniform. Pure and deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise
from typing import Literal

from pydantic import Field

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)

State = Literal["UP", "FLAT", "DOWN"]
#: Course order — also the MAP tie-break order.
STATES: tuple[State, ...] = ("UP", "FLAT", "DOWN")


class BayesianTrendParams(StrategyParams):
    """Parameters for :class:`BayesianTrendStrategy`. Defaults match course Algo 33."""

    drift: float = Field(default=0.001, gt=0.0)
    trend_sigma: float = Field(default=0.002, gt=0.0)
    flat_sigma: float = Field(default=0.0008, gt=0.0)
    threshold: float = Field(default=0.6, gt=1 / 3, lt=1.0)
    replay_bars: int = Field(default=20, ge=1)

    @property
    def required_history(self) -> int:
        """``replay_bars`` returns need one more close."""
        return self.replay_bars + 1


def _log_normal_pdf(x: float, mean: float, sigma: float) -> float:
    return -math.log(sigma * math.sqrt(2 * math.pi)) - 0.5 * ((x - mean) / sigma) ** 2


def posterior(closes: Sequence[float], params: BayesianTrendParams) -> dict[State, float]:
    """Regime probabilities after replaying the latest ``replay_bars`` returns."""
    means: dict[State, tuple[float, float]] = {
        "UP": (params.drift, params.trend_sigma),
        "FLAT": (0.0, params.flat_sigma),
        "DOWN": (-params.drift, params.trend_sigma),
    }
    log_post = dict.fromkeys(STATES, math.log(1 / 3))
    window = closes[-(params.replay_bars + 1) :]
    for previous, current in pairwise(window):
        if previous <= 0:
            continue
        delta = (current - previous) / previous
        for state in STATES:
            mean, sigma = means[state]
            log_post[state] += _log_normal_pdf(delta, mean, sigma)
        peak = max(log_post.values())
        total = peak + math.log(sum(math.exp(v - peak) for v in log_post.values()))
        log_post = {state: value - total for state, value in log_post.items()}
    return {state: math.exp(value) for state, value in log_post.items()}


def most_likely(probabilities: dict[State, float]) -> tuple[State, float]:
    """The MAP regime and its probability (ties resolved UP → FLAT → DOWN)."""
    best = max(STATES, key=lambda state: probabilities[state])
    return best, probabilities[best]


class BayesianTrendStrategy:
    """Bayesian regime classifier signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter a confident up-regime; exit a confident down-regime."""
        if not isinstance(params, BayesianTrendParams):
            raise TypeError(
                f"BayesianTrendStrategy requires BayesianTrendParams, got {type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the Bayesian update")

        probabilities = posterior([bar.close for bar in bars], params)
        state, probability = most_likely(probabilities)
        confident = probability >= params.threshold
        summary = (
            f"P(up) {probabilities['UP']:.2f}, P(flat) {probabilities['FLAT']:.2f}, "
            f"P(down) {probabilities['DOWN']:.2f} over {params.replay_bars} bars"
        )
        if position is not None and position.is_open:
            if state == "DOWN" and confident:
                return Signal.exit(f"confident down-regime: {summary}")
            return Signal.hold(f"no confident down-regime: {summary}")
        if state == "UP" and confident:
            return Signal.enter_long(f"confident up-regime: {summary}")
        return Signal.hold(f"no confident up-regime: {summary}")
