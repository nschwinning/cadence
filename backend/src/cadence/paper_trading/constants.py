"""Enums for the paper-trading capability.

``ScheduleMode`` values mirror trading-bot exactly (upper-cased). Trade side and
order status reuse the broker vocabulary (:mod:`cadence.broker.models`) so a
recorded paper trade lines up with the broker fills it came from.
"""

from __future__ import annotations

from enum import StrEnum

from cadence.broker.models import OrderStatus


class ScheduleMode(StrEnum):
    """How a paper-trading session is run automatically.

    - ``MANUAL``: no automatic runs; only explicit user actions touch it.
    - ``SCHEDULED``: run by the periodic intraday signal-scan cron.
    - ``DAILY_REBALANCING``: rebalanced once per weekday morning by the AI
      rebalance cron (AI buy-and-hold portfolios opting into daily rebalancing).
    """

    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    DAILY_REBALANCING = "DAILY_REBALANCING"


class SessionStatus(StrEnum):
    """Lifecycle status of a paper-trading session."""

    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class RunStatus(StrEnum):
    """Outcome of a single session run."""

    SUCCESS = "success"
    FAILURE = "failure"


class Benchmark(StrEnum):
    """A market benchmark index a paper-trading session can be compared against.

    The member *value* is the stable identifier persisted on a session and used in
    the API; :data:`BENCHMARK_DISPLAY_NAMES` maps it to a human-readable name and
    :data:`BENCHMARK_SYMBOLS` to the market-data symbol the system fetches. Sessions
    store the identifier, never the raw symbol, so the symbol mapping can change
    without touching stored data. All catalog entries are **price-return** index
    tickers (dividends excluded): the session valuation does not credit dividends
    either, so a price-return comparison is apples-to-apples.
    """

    SP500 = "SP500"
    DJIA = "DJIA"
    NYSE_COMPOSITE = "NYSE_COMPOSITE"
    NASDAQ_COMPOSITE = "NASDAQ_COMPOSITE"
    NASDAQ_100 = "NASDAQ_100"
    RUSSELL_2000 = "RUSSELL_2000"
    SP100 = "SP100"
    WILSHIRE_5000 = "WILSHIRE_5000"


#: Human-readable display name per benchmark, surfaced in the UI catalog.
BENCHMARK_DISPLAY_NAMES: dict[Benchmark, str] = {
    Benchmark.SP500: "S&P 500",
    Benchmark.DJIA: "Dow Jones Industrial Average",
    Benchmark.NYSE_COMPOSITE: "NYSE Composite",
    Benchmark.NASDAQ_COMPOSITE: "Nasdaq Composite",
    Benchmark.NASDAQ_100: "Nasdaq-100",
    Benchmark.RUSSELL_2000: "Russell 2000",
    Benchmark.SP100: "S&P 100",
    Benchmark.WILSHIRE_5000: "Wilshire 5000",
}

#: Market-data (yfinance) symbol the ingestion job fetches per benchmark.
BENCHMARK_SYMBOLS: dict[Benchmark, str] = {
    Benchmark.SP500: "^GSPC",
    Benchmark.DJIA: "^DJI",
    Benchmark.NYSE_COMPOSITE: "^NYA",
    Benchmark.NASDAQ_COMPOSITE: "^IXIC",
    Benchmark.NASDAQ_100: "^NDX",
    Benchmark.RUSSELL_2000: "^RUT",
    Benchmark.SP100: "^OEX",
    Benchmark.WILSHIRE_5000: "^W5000",
}


def benchmark_display_name(benchmark: Benchmark) -> str:
    """Return the human-readable display name for ``benchmark``."""
    return BENCHMARK_DISPLAY_NAMES[benchmark]


def benchmark_symbol(benchmark: Benchmark) -> str:
    """Return the market-data symbol the system fetches for ``benchmark``."""
    return BENCHMARK_SYMBOLS[benchmark]


#: Default trade side/status come from the broker vocabulary; imported here for
#: convenience so the paper-trading layer has a single enums module.
DEFAULT_ORDER_STATUS = "filled"
DEFAULT_RUN_TRIGGER = "scheduled"

#: Order statuses that will never change again, so reconciliation stops
#: re-querying them. Mirrors :attr:`cadence.broker.models.Order.is_complete`;
#: ``submitted``, ``pending``, and ``partially_filled`` remain non-terminal.
TERMINAL_ORDER_STATUSES = frozenset(
    {
        OrderStatus.FILLED.value,
        OrderStatus.CANCELLED.value,
        OrderStatus.REJECTED.value,
    }
)

#: Trading days per year used to annualise the daily-return Sharpe ratio
#: (``sharpe × √252``). The conventional US-equity trading-day count.
SHARPE_TRADING_DAYS_PER_YEAR = 252

#: Minimum number of daily returns a session needs before its Sharpe ratio is
#: reported. Below this the sample is too small to be meaningful, so the ratio is
#: withheld (``None``) and the UI shows "not yet available". ~20 ≈ one trading
#: month.
SHARPE_MIN_RETURNS = 20
