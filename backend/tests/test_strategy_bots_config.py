"""Strategy-bot subsystem configuration defaults."""

from __future__ import annotations

from cadence.config import Settings
from cadence.strategy_bots.constants import BarTimeframe, MarketDataFeed


def test_bot_settings_have_sensible_defaults() -> None:
    """A fresh Settings carries the documented bot defaults (5-min cadence, iex)."""
    settings = Settings()

    assert settings.BOT_TICK_INTERVAL_MINUTES == 5
    assert settings.BOT_SIGNAL_BAR_TIMEFRAME == BarTimeframe.FIVE_MIN.value
    assert settings.BOT_MARKET_DATA_FEED == MarketDataFeed.IEX.value
    assert settings.BOT_MARKET_DATA_MODE == "rest"
    assert settings.BOT_BAR_FRESHNESS_MINUTES == 10
    assert settings.BOT_CASH_BUFFER_PCT == 0.02
    assert settings.BOT_DRAWDOWN_STOP_PCT == 0.25


def test_bot_feed_and_timeframe_defaults_are_valid_enum_values() -> None:
    """The string defaults round-trip to their closed enums (no typos)."""
    settings = Settings()

    assert MarketDataFeed(settings.BOT_MARKET_DATA_FEED) is MarketDataFeed.IEX
    assert (
        BarTimeframe(settings.BOT_SIGNAL_BAR_TIMEFRAME) is BarTimeframe.FIVE_MIN
    )
