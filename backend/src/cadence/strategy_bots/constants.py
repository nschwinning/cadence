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
    """Registered strategy identifiers.

    The value is the stable key stored on ``bot_sessions.strategy_key`` and used
    to resolve the strategy implementation in :mod:`.registry`.
    """

    MA_CROSSOVER = "ma_crossover"
    RSI_MEAN_REVERSION = "rsi_mean_reversion"
    DONCHIAN_BREAKOUT = "donchian_breakout"


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
    StrategyKey.RSI_MEAN_REVERSION: "RSI Mean Reversion",
    StrategyKey.DONCHIAN_BREAKOUT: "Donchian Range Breakout",
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
    StrategyKey.RSI_MEAN_REVERSION: (
        "The RSI Mean Reversion strategy is a counter-trend rule built on the "
        "Relative Strength Index (RSI), a 0–100 momentum gauge of recent gains "
        "versus losses. When RSI falls below the oversold level (default 30) the "
        "price is considered stretched to the downside and the bot buys the dip; it "
        "then exits once RSI reverts back above the exit level (default 50), the "
        "mean-reversion target. Between those levels it holds. It is deterministic "
        "and long-only — it never shorts an overbought reading — and leaves "
        "take-profit, stop-loss, and the drawdown kill-switch to the bot's risk "
        "controls."
    ),
    StrategyKey.DONCHIAN_BREAKOUT: (
        "The Donchian Range Breakout strategy follows breakouts of a price channel "
        "— the highest high and lowest low of a recent window of bars. The bot enters "
        "a long position when the price closes above the top of the channel, reading "
        "the breakout as the start of a trend. It offers two versions. The Turtle "
        "rolling channel exits when the price closes below the bottom of a shorter "
        "channel, following the trend until it breaks down. The Locked channel instead "
        "freezes once a trade is open and leaves the exit entirely to the bot's "
        "risk controls; its entry band can be padded outward by a multiple of recent "
        "volatility (an ATR buffer) to filter out false breakouts. Both are "
        "deterministic and long-only — a downward breakout never opens a short — and "
        "leave position sizing, take-profit, stop-loss, and the drawdown kill-switch "
        "to the bot's risk controls."
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
