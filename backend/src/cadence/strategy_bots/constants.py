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


class StopReason(StrEnum):
    """Why a bot session transitioned to STOPPED.

    ``MANUAL`` is a client-initiated stop; ``DRAWDOWN_KILL_SWITCH`` is the
    whole-session drawdown kill-switch firing during a tick; ``ORCHESTRATOR`` is a bot
    orchestrator stopping one of its bots (or the whole orchestrator being stopped).
    Stored as free text on ``bot_sessions.stop_reason`` (null for sessions stopped
    before this was recorded).
    """

    DRAWDOWN_KILL_SWITCH = "drawdown_kill_switch"
    MANUAL = "manual"
    ORCHESTRATOR = "orchestrator"


class BotOrigin(StrEnum):
    """Who created a bot session.

    ``MANUAL`` is a session built through the client API (the build form);
    ``ORCHESTRATOR`` is a session deployed by a bot orchestrator (which is also
    referenced by ``bot_sessions.orchestrator_id``). Stored as free text on
    ``bot_sessions.origin`` (server default ``manual`` for older rows).
    """

    MANUAL = "manual"
    ORCHESTRATOR = "orchestrator"


class StrategyKey(StrEnum):
    """Registered strategy identifiers.

    The value is the stable key stored on ``bot_sessions.strategy_key`` and used
    to resolve the strategy implementation in :mod:`.registry`.
    """

    MA_CROSSOVER = "ma_crossover"
    RSI_MEAN_REVERSION = "rsi_mean_reversion"
    DONCHIAN_BREAKOUT = "donchian_breakout"
    ROLLING_AVERAGE_REVERSION = "rolling_average_reversion"
    ATR_BAND_TREND = "atr_band_trend"
    ADX_TREND = "adx_trend"
    MACD_MOMENTUM = "macd_momentum"
    HEIKIN_ASHI_TREND = "heikin_ashi_trend"
    HMA_TREND = "hma_trend"
    MA_RIBBON = "ma_ribbon"
    VAMA = "vama"
    PRICE_VELOCITY_REVERSAL = "price_velocity_reversal"
    TREND_CONFIRMATION = "trend_confirmation"
    VOLUME_BREAKOUT = "volume_breakout"


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
    StrategyKey.ROLLING_AVERAGE_REVERSION: "Rolling-Average Reversion",
    StrategyKey.ATR_BAND_TREND: "ATR-Band Trend",
    StrategyKey.ADX_TREND: "ADX Trend Strength",
    StrategyKey.MACD_MOMENTUM: "MACD Momentum",
    StrategyKey.HEIKIN_ASHI_TREND: "Heikin-Ashi Trend",
    StrategyKey.HMA_TREND: "HMA Trend",
    StrategyKey.MA_RIBBON: "MA Ribbon",
    StrategyKey.VAMA: "VAMA",
    StrategyKey.PRICE_VELOCITY_REVERSAL: "Price Velocity Reversal",
    StrategyKey.TREND_CONFIRMATION: "Trend Confirmation",
    StrategyKey.VOLUME_BREAKOUT: "Volume Breakout",
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
    StrategyKey.ROLLING_AVERAGE_REVERSION: (
        "The Rolling-Average Reversion strategy buys when price has dropped below its "
        "recent average and sells as it snaps back. It tracks a rolling average over "
        "the last N bars — a simple average of closes, an average of typical prices "
        "(high + low + close) / 3, or a volume-weighted average — and measures how "
        "far the latest close sits below it, either as a percentage band or as a "
        "z-score in standard deviations. A zero band means any close below the "
        "average is a buy. It either exits once price reverts back to (or above) the "
        "exit level, or holds and lets the take-profit / stop-loss bracket close the "
        "trade. It is deterministic and long-only — a price above its average never "
        "opens a short — and leaves sizing and the drawdown kill-switch to the bot's "
        "risk controls."
    ),
    StrategyKey.ATR_BAND_TREND: (
        "The ATR-Band Trend strategy rides trends that break out of a volatility band "
        "around the recent price. It measures volatility as the average move from one "
        "close to the next (an ATR) and places bands a multiple of it around a midline. "
        "In the SuperTrend version the midline is the middle of the recent range and "
        "the bands only tighten while a trend lasts; the bot buys when the trend is up "
        "and the price sits above the SuperTrend line, then holds and lets the "
        "take-profit / stop-loss bracket close the trade. In the Keltner version the "
        "midline is a simple moving average; the bot buys when the price breaks above "
        "the upper band and sells when it falls back below the average. It is "
        "deterministic and long-only, and leaves sizing and the drawdown kill-switch to "
        "the bot's risk controls."
    ),
    StrategyKey.ADX_TREND: (
        "The ADX Trend Strength strategy only trades trends that are strong. It compares "
        "how far each bar's high rises against how far its low falls, scaled by the "
        "bar's true range, to get two directional readings: +DI for buying pressure and "
        "−DI for selling pressure. How far apart they are gives the trend strength, and "
        "the ADX averages it over recent bars. The bot buys when the ADX is above its "
        "threshold and +DI leads −DI — a strong up-trend — and sells once the ADX falls "
        "back below the threshold and the trend has lost its strength. It is "
        "deterministic and long-only, and leaves take-profit, stop-loss, sizing and the "
        "drawdown kill-switch to the bot's risk controls."
    ),
    StrategyKey.MACD_MOMENTUM: (
        "The MACD Momentum strategy buys when upward momentum is confirmed. It follows "
        "two exponential moving averages of the closing price — a fast one and a slow "
        "one — and their difference, the MACD, plus a signal line that smooths the MACD. "
        "When the MACD crosses above its signal line while the MACD itself is above zero "
        "(the fast average already leads the slow one), momentum has turned up on the "
        "bullish side and the bot enters a long position. It then holds and lets the "
        "take-profit / stop-loss bracket close the trade. It is deterministic and "
        "long-only, and leaves sizing and the drawdown kill-switch to the bot's risk "
        "controls."
    ),
    StrategyKey.HEIKIN_ASHI_TREND: (
        "The Heikin-Ashi Trend strategy rides runs of smoothed candles. It redraws each "
        "price bar as a Heikin-Ashi candle — its close is the average of the bar's open, "
        "high, low and close, and its open is the midpoint of the previous Heikin-Ashi "
        "candle — which filters out much of the bar-to-bar noise. A green candle (close "
        "above open) means buyers are in control: the bot buys. The first red candle "
        "means the run is over: the bot sells. An optional volume filter only buys when "
        "the bar's volume is above its recent average and also sells when volume fades. "
        "It is deterministic and long-only, and leaves sizing and the drawdown "
        "kill-switch to the bot's risk controls."
    ),
    StrategyKey.HMA_TREND: (
        "The HMA Trend strategy follows trends with Hull Moving Averages, which track "
        "price with far less lag than ordinary moving averages. It keeps a fast and a "
        "slow Hull average of the closing price. When the fast one is above the slow "
        "one and still rising, an up-trend is under way and the bot buys. It sells on a "
        "trend reversal — the fast average dropping below the slow one while falling. "
        "It is deterministic and long-only, and leaves take-profit, stop-loss, sizing "
        "and the drawdown kill-switch to the bot's risk controls."
    ),
    StrategyKey.MA_RIBBON: (
        "The MA Ribbon strategy waits until the trend agrees on every horizon. It keeps "
        "three simple moving averages of the closing price — fast, mid and slow — like "
        "the strands of a ribbon. When they stack in order, fast above mid above slow, "
        "prices are rising over the short, medium and longer term at once and the bot "
        "buys. It then holds and lets the take-profit / stop-loss bracket close the "
        "trade. It is deterministic and long-only, and leaves sizing and the drawdown "
        "kill-switch to the bot's risk controls."
    ),
    StrategyKey.VAMA: (
        "The VAMA strategy follows a volatility-adaptive moving average. Each bar the "
        "average moves a fraction of the way toward the latest close; that fraction is "
        "its speed. With adaptive smoothing the speed rises when the market is volatile "
        "and falls when it is calm, so the average keeps up with fast moves without "
        "chasing noise in quiet ones; without it the speed is fixed, as in the course. "
        "The bot buys when the price is above the average and sells when it falls back "
        "to or below it. It is deterministic and long-only, and leaves sizing and the "
        "drawdown kill-switch to the bot's risk controls."
    ),
    StrategyKey.PRICE_VELOCITY_REVERSAL: (
        "The Price Velocity Reversal strategy buys the moment a sharp drop starts to run "
        "out of steam. It measures how fast the price is moving — its velocity, the "
        "latest bar's percentage change — and whether that move is speeding up or "
        "slowing down. When the price is falling faster than a threshold but by less "
        "than on the bar before, sellers are losing momentum and the bot buys, betting "
        "on a bounce. It sells as soon as the price turns up again. It is deterministic "
        "and long-only, and leaves take-profit, stop-loss, sizing and the drawdown "
        "kill-switch to the bot's risk controls."
    ),
    StrategyKey.TREND_CONFIRMATION: (
        "The Trend Confirmation strategy only buys when several independent trend "
        "readings agree. The fast moving average must be above the slow one (the trend), "
        "the MACD histogram must be positive (momentum building) and the RSI must be "
        "strong but not overheated; optionally the rate of change must be positive and "
        "on-balance volume rising. It buys once every active check passes and sells as "
        "soon as one fails — with a little slack on the RSI and never because the RSI is "
        "too high, so a strong trend is not sold early. It uses the same indicator maths "
        "as the AI portfolio's technical gate, tuned for intraday bars. It is "
        "deterministic and long-only, and leaves take-profit, stop-loss, sizing and the "
        "drawdown kill-switch to the bot's risk controls."
    ),
    StrategyKey.VOLUME_BREAKOUT: (
        "The Volume Breakout strategy trades moves that heavy volume confirms, in one of "
        "three versions. Spike buys when the price breaks above its recent high on a bar "
        "whose volume is well above average, and sells when it breaks below the recent "
        "low on a volume spike. VROC watches for a sudden surge in volume while the price "
        "is still in a tight range, then buys the first close above that range and sells "
        "once volume starts falling. Chaikin tracks whether volume flows in on up-closes "
        "or down-closes (accumulation versus distribution) and buys when that flow turns "
        "positive, selling when it turns negative. Volume is naturally heavier near the "
        "open and close, so signals cluster there. It is deterministic and long-only, and "
        "leaves take-profit, stop-loss, sizing and the drawdown kill-switch to the bot's "
        "risk controls."
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
