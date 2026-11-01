"""Feature definitions, signal status, and labels for the price-ML capability.

Tunable knobs (horizon, retrain cadence, minimum bar count, staleness bound,
random seed, model version) live in :mod:`cadence.config` as settings; this
module holds only the deterministic, non-configurable definitions — the feature
column names and the small enums the stored signal uses.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

#: Timezone the price-ML dates are anchored to (US market close), matching the
#: nightly precompute cron schedule — the single clock seam for "today".
MARKET_TZ = ZoneInfo("America/New_York")


def today() -> date:
    """Today's calendar date in the market-close timezone (tz-aware clock seam)."""
    return datetime.now(tz=MARKET_TZ).date()


class SignalDirection(StrEnum):
    """Predicted direction of the forward return."""

    UP = "up"
    DOWN = "down"


class SignalStatus(StrEnum):
    """Resolution status of a per-ticker price-ML block handed to the agent."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


#: Trailing-return lag windows (trading days). Each becomes a ``ret_<w>d``
#: feature equal to the trailing ``w``-day percentage return known at the row's
#: date — the "lagged price-history returns" the spec calls for.
LAG_RETURN_WINDOWS: tuple[int, ...] = (1, 5, 10, 21, 63)

# --- Indicator feature periods (derived from the stored daily closes) --------
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
SMA_SHORT = 50
SMA_LONG = 200
VOL_WINDOW = 21
BB_PERIOD = 20
BB_STD = 2.0

#: Indicator feature column names, in a fixed order. These mirror the
#: scale-free technical indicators the nightly TI run computes, derived here
#: from the already-stored price history so the same feature can be built at
#: every historical row (training) and at the latest row (inference).
INDICATOR_FEATURE_COLUMNS: tuple[str, ...] = (
    "rsi_14",
    "macd_hist",
    "vol_21",
    "close_sma50",
    "close_sma200",
    "sma50_sma200",
    "bb_pctb",
)

#: The complete, ordered feature vector: lagged returns followed by indicators.
#: Order is load-bearing — it is the model's feature-schema fingerprint and is
#: stored with the cached artifact so an incompatible cache triggers a retrain.
FEATURE_COLUMNS: tuple[str, ...] = (
    tuple(f"ret_{window}d" for window in LAG_RETURN_WINDOWS) + INDICATOR_FEATURE_COLUMNS
)
