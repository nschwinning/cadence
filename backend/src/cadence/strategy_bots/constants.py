"""Enums and fixed catalogs for the strategy-bot subsystem.

Deliberately separate from the paper-trading constants: the bot domain evolves on
its own cadence (intraday, deterministic) and must not couple to AI-session
vocabulary. Values are part of the API contract.
"""

from __future__ import annotations

from enum import StrEnum


class BotSessionStatus(StrEnum):
    """Lifecycle state of a bot session.

    ``ACTIVE`` sessions are ticked and snapshotted; ``STOPPED`` sessions are flat
    and no longer ticked (reached by a manual stop or the drawdown kill-switch);
    ``ARCHIVED`` sessions are soft-hidden from the default listing. Only a
    ``STOPPED`` session may be archived.
    """

    ACTIVE = "active"
    STOPPED = "stopped"
    ARCHIVED = "archived"


class StrategyKey(StrEnum):
    """Registered strategy identifiers. v1 ships a single strategy.

    The value is the stable key stored on ``bot_sessions.strategy_key`` and used
    to resolve the strategy implementation in :mod:`.registry`.
    """

    MA_CROSSOVER = "ma_crossover"


class SizingMethod(StrEnum):
    """How a bot sizes a new long position within its shared capital pool.

    ``ATR_RISK`` targets an equal dollar risk per name (risk dollars divided by a
    multiple of the symbol's Average True Range); ``ALL_IN`` buys the greatest whole
    number of shares affordable from available cash. Both are additionally bounded by
    the per-name cap and remaining cash. ``ALL_IN`` reproduces the legacy single-asset
    behaviour and is what migrated single-asset sessions use.
    """

    ATR_RISK = "atr_risk"
    ALL_IN = "all_in"


#: Human-facing display names for the strategy catalog (``/api/v1/bots`` reads).
STRATEGY_DISPLAY_NAMES: dict[StrategyKey, str] = {
    StrategyKey.MA_CROSSOVER: "Moving-Average Crossover",
}

#: Human-readable explanations for the strategy catalog, shown on the strategy
#: explanation page. Describes what each strategy does in plain language.
STRATEGY_EXPLANATIONS: dict[StrategyKey, str] = {
    StrategyKey.MA_CROSSOVER: (
        "The Moving-Average Crossover strategy follows trends using two simple "
        "moving averages of the closing price — a faster, shorter-window average and "
        "a slower, longer-window average. When the fast average crosses above the "
        "slow average it reads as upward momentum and the bot enters a long position; "
        "when the fast average crosses back below the slow average the trend is "
        "considered over and the bot exits. Between crossovers it holds its current "
        "state. It is a deterministic, long-only trend-following rule: it never "
        "shorts, and it waits for a confirmed cross rather than predicting turns."
    ),
}


class BotValueResolution(StrEnum):
    """Resolution of a bot session's value-history read.

    ``FIVE_MIN`` and ``HOURLY`` are downsampled from the intraday
    ``bot_value_points`` (so they span roughly the retention window);
    ``DAILY`` and ``MONTHLY`` come from the daily ``bot_value_snapshots``
    equity curve. ``DAILY`` is the default. The value is part of the API
    contract (the ``resolution`` query param and response field).
    """

    FIVE_MIN = "5min"
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class BarTimeframe(StrEnum):
    """Intraday bar timeframe for signal computation.

    The value is the Alpaca market-data ``timeframe`` string. v1 defaults to
    5-minute bars; the enum keeps the contract closed so a typo cannot reach the
    data API.
    """

    ONE_MIN = "1Min"
    FIVE_MIN = "5Min"
    FIFTEEN_MIN = "15Min"
    ONE_HOUR = "1Hour"


class MarketDataFeed(StrEnum):
    """Alpaca market-data feed selector.

    ``IEX`` is real-time on the free tier (single exchange, can be sparse);
    ``SIP`` is the consolidated feed, real-time only on a paid subscription. The
    bot tick always sets this explicitly rather than relying on the account
    default (which trips the free-tier 15-minute SIP restriction).
    """

    IEX = "iex"
    SIP = "sip"
