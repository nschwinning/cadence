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


#: Human-facing display names for the strategy catalog (``/api/v1/bots`` reads).
STRATEGY_DISPLAY_NAMES: dict[StrategyKey, str] = {
    StrategyKey.MA_CROSSOVER: "Moving-Average Crossover",
}


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
