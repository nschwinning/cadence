"""The Multi-Signal Consensus strategy — a long-only, vote-based mean-reversion entry.

Ported from the course "Algo 43 Multi-Signal Mean Reversion Consensus Engine". Over the
latest ``window`` closes eight simple mean-reversion signals each vote +1 (oversold), −1
(overbought) or 0: z-score, SMA deviation, RSI, Bollinger bands, percentile rank, median,
short gradient and range position. While flat the bot enters long once the vote sum reaches
``consensus``; while holding it holds, leaving every exit to the engine's take-profit /
stop-loss bracket and drawdown kill-switch — the course exits only that way.

Deviations from the course: its RSI needs ``rsi_period + 1`` prices but the script keeps
only ``window`` (10 < 15), so RSI never voted — here RSI reads its own closes, so all eight
signals vote. The course's absolute ₹ thresholds on a ~₹1,000 price become percentages of
price (median ±0.2%, range 0.1%). The course short leg is dropped (Cadence is long-only);
overbought votes still lower the score. Pure and deterministic.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from pydantic import Field

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)

# The course's fixed vote thresholds.
_Z_LIMIT = 1.0
_SMA_BAND = 0.01
_RSI_OVERSOLD = 30.0
_RSI_OVERBOUGHT = 70.0
_RANK_LOW = 0.1
_RANK_HIGH = 0.9
_MEDIAN_BAND = 0.002
_GRADIENT_BARS = 5
_RANGE_BAND = 0.001


class SignalConsensusParams(StrategyParams):
    """Parameters for :class:`SignalConsensusStrategy`. Defaults match course Algo 43."""

    window: int = Field(default=10, ge=_GRADIENT_BARS)
    consensus: int = Field(default=3, ge=1, le=8)
    rsi_period: int = Field(default=14, ge=2)
    bb_k: float = Field(default=2.0, gt=0.0)

    @property
    def required_history(self) -> int:
        """The voting window, or RSI's own closes when it needs more."""
        return max(self.window, self.rsi_period + 1)


def _sign_vote(value: float, low: float, high: float) -> int:
    """+1 below ``low``, −1 above ``high``, else 0."""
    if value < low:
        return 1
    if value > high:
        return -1
    return 0


def simple_rsi(closes: Sequence[float]) -> float:
    """The course RSI: simple means of gains and losses (100 when the mean loss is 0)."""
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gain = sum(max(d, 0.0) for d in diffs) / len(diffs)
    loss = sum(max(-d, 0.0) for d in diffs) / len(diffs)
    if loss == 0:
        return 100.0
    return 100 - 100 / (1 + gain / loss)


def votes(closes: Sequence[float], params: SignalConsensusParams) -> dict[str, int]:
    """Each signal's vote for the latest close, in the course's order."""
    window = list(closes[-params.window :])
    close = window[-1]
    mean = sum(window) / len(window)
    sigma = statistics.pstdev(window)
    median = statistics.median(window)
    low, high = min(window), max(window)

    z = 0 if sigma == 0 else _sign_vote((close - mean) / sigma, -_Z_LIMIT, _Z_LIMIT)
    rank = sum(1 for c in window if c < close) / len(window)
    gradient_mean = sum(window[-_GRADIENT_BARS:]) / _GRADIENT_BARS
    if close >= high * (1 - _RANGE_BAND):
        range_vote = -1
    elif close <= low * (1 + _RANGE_BAND):
        range_vote = 1
    else:
        range_vote = 0

    return {
        "Z": z,
        "SMA": _sign_vote((close - mean) / mean, -_SMA_BAND, _SMA_BAND),
        "RSI": _sign_vote(
            simple_rsi(closes[-(params.rsi_period + 1) :]), _RSI_OVERSOLD, _RSI_OVERBOUGHT
        ),
        "BB": _sign_vote(close, mean - params.bb_k * sigma, mean + params.bb_k * sigma),
        "PCTL": _sign_vote(rank, _RANK_LOW, _RANK_HIGH),
        "MED": _sign_vote((close - median) / median, -_MEDIAN_BAND, _MEDIAN_BAND),
        "GRAD": _sign_vote(close - gradient_mean, 0.0, 0.0),
        "RANGE": range_vote,
    }


class SignalConsensusStrategy:
    """Vote-based mean-reversion signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter on an oversold consensus; hold while in position."""
        if not isinstance(params, SignalConsensusParams):
            raise TypeError(
                "SignalConsensusStrategy requires SignalConsensusParams, got "
                f"{type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the consensus votes")
        if position is not None and position.is_open:
            return Signal.hold("consensus holds while in position; exit deferred to the engine")

        closes = [bar.close for bar in bars]
        if any(not math.isfinite(c) or c <= 0 for c in closes[-params.required_history :]):
            return Signal.hold("non-positive close in the voting window")
        ballot = votes(closes, params)
        score = sum(ballot.values())
        tally = ", ".join(f"{name} {vote:+d}" for name, vote in ballot.items())
        summary = f"{tally}; score {score} vs consensus {params.consensus}"
        if score >= params.consensus:
            return Signal.enter_long(f"oversold consensus: {summary}")
        return Signal.hold(f"no consensus: {summary}")
