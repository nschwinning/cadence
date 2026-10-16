"""Indicator periods, gate thresholds, and run-lifecycle constants.

All thresholds are plain module constants so they can be tuned without a schema
or prompt change (design decision: "thresholds as constants").
"""

from __future__ import annotations

from enum import StrEnum

# --- Indicator periods (close+volume subset) -------------------------------
SMA_SHORT = 50
SMA_LONG = 200
EMA_SPAN = 20
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_PERIOD = 14
ROC_PERIOD = 120
BB_PERIOD = 20
BB_STD = 2.0
HVOL_PERIOD = 20
AVG_VOL_PERIOD = 50
HIGH_52W = 252
DRAWDOWN_PERIOD = 252

#: Lookback (bars) for the SMA200 slope (percent change over the window).
SLOPE_WINDOW = 20
#: Lookback (bars) for the OBV change and the OBV/price divergence proxy.
OBV_CHANGE_WINDOW = 20
DIVERGENCE_LOOKBACK = 20

#: Trading days per year, for annualising historical volatility.
TRADING_DAYS = 252

# --- Deterministic uptrend gate thresholds (tunable) -----------------------
#: Regime: close > SMA200 AND SMA50 > SMA200 AND SMA200 slope >= this.
SMA_SLOPE_MIN = 0.0
#: Momentum: MACD histogram strictly above this.
MACD_HIST_MIN = 0.0
#: Momentum: RSI(14) strictly above this.
RSI_MOMENTUM_MIN = 50.0
#: Momentum: ROC(120) strictly above this.
ROC_MOMENTUM_MIN = 0.0

# --- Reversal-flag thresholds (tunable) ------------------------------------
#: RSI band above which a turn-down counts as an RSI rollover.
RSI_OVERBOUGHT = 70.0
#: SMA200 slope below this counts as "flattening" (covers near-zero/declining).
SLOPE_FLATTEN_EPS = 0.005

# --- Watchlist short-window profile ----------------------------------------
#: Minimum daily bars for a watchlist asset's short-window technical profile to
#: be meaningful. Below this the asset is marked insufficient-history instead of
#: surfacing mostly-absent values. Tunable: MACD needs ~34 bars (slow EMA 26 + 9
#: signal), so 40 leaves a clean margin.
WATCHLIST_MIN_BARS = 40

#: The short-window indicator keys surfaced for watchlist assets — the
#: momentum / mean-reversion subset meaningful for young names. The long-window
#: set (SMA50/200 and their ratios, SMA200 slope, ROC120, 52-week-high distance,
#: 252-day drawdown) and the uptrend trend-gate verdict are NOT presented as a
#: watchlist trading signal.
WATCHLIST_SHORT_WINDOW_KEYS = (
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "ema_20",
    "bb_pctb",
    "bb_width",
    "hvol_20",
    "vol_ratio_50",
    "obv_change_20d",
)

#: The reversal flags whose inputs are entirely short-window (so they are
#: meaningful for watchlist assets). ``sma200_slope_flattening`` is excluded —
#: it depends on the long-window SMA200.
WATCHLIST_SHORT_WINDOW_REVERSAL_KEYS = (
    "rev_macd_hist_rollover",
    "rev_rsi_rollover",
    "rev_return_decel",
    "rev_obv_price_divergence",
)


class RunPhase(StrEnum):
    """Lifecycle of a technical-indicator precompute run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


#: Phases from which a run never transitions again.
TERMINAL_PHASES = frozenset({RunPhase.COMPLETED, RunPhase.FAILED})
