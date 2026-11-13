"""Unit tests for the strategy-bot session service, tick runner, and KPIs."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session
from tests.fakes import FakeBotSummaryAgent, RecordingNotifier

from cadence.assets.models import Asset
from cadence.broker.models import OrderSide
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.paper_trading.constants import Benchmark
from cadence.paper_trading.models import BenchmarkPrice
from cadence.strategy_bots import service
from cadence.strategy_bots.constants import BotValueResolution
from cadence.strategy_bots.errors import (
    BotSessionNotArchivableError,
    BotSessionNotStoppedError,
    IneligibleAssetError,
    InvalidBotBenchmarkError,
    InvalidBotConfigError,
    UnknownPresetError,
    UnknownStrategyError,
)
from cadence.strategy_bots.market_data import BarsResult
from cadence.strategy_bots.models import (
    BotPosition,
    BotSession,
    BotTrade,
    BotValuePoint,
    BotValueSnapshot,
)
from cadence.strategy_bots.strategy import Bar

_NOW = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
_PARAMS = {"fast_period": 2, "slow_period": 3}


def _add_asset(
    db_session: Session,
    ticker: str = "AAPL",
    *,
    category: str = "stock",
    is_eligible: bool = True,
) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category=category,
        currency="USD",
        is_eligible=is_eligible,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.flush()
    return asset


class _OpenableBroker(StubBroker):
    """StubBroker with a toggleable market-open state."""

    def __init__(self, *, market_open: bool = True) -> None:
        super().__init__()
        self._market_open = market_open

    def is_market_open(self) -> bool:
        return self._market_open


class _PerSymbolMarketData:
    """Returns a preset bar series per symbol (ticker/alpaca_symbol keyed).

    A symbol absent from the mapping is treated as having no fresh data this tick.
    """

    def __init__(
        self, series: dict[str, list[float]], *, fresh: bool = True
    ) -> None:
        self._series = series
        self._fresh = fresh

    def latest_bars(
        self, symbol: str, timeframe: str, count: int, *, now: datetime
    ) -> BarsResult:
        closes = self._series.get(symbol)
        if closes is None:
            return BarsResult(bars=[], as_of=None, fresh=False)
        bars = [
            Bar(timestamp=now, open=c, high=c, low=c, close=c, volume=1000.0)
            for c in closes
        ]
        as_of = bars[-1].timestamp if bars else None
        return BarsResult(bars=bars, as_of=as_of, fresh=self._fresh)


def _create(db_session: Session, **overrides: object) -> BotSession:
    kwargs: dict[str, object] = {
        "strategy_key": "ma_crossover",
        "tickers": ["AAPL"],
        "initial_capital": 100_000.0,
        "benchmark": "SP500",
        "strategy_params": dict(_PARAMS),
        "sizing_method": "all_in",
    }
    kwargs.update(overrides)
    return service.create_bot_session(db_session, **kwargs)  # type: ignore[arg-type]


# Lifecycle ---------------------------------------------------------------
def test_create_bot_session_persists_active(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    assert bot.id is not None
    assert bot.status == "active"
    assert [s.ticker for s in bot.symbols] == ["AAPL"]
    assert bot.benchmark == "SP500"
    assert bot.allocated_capital == 100_000.0
    assert bot.cash == 100_000.0
    assert bot.peak_value == 100_000.0
    assert bot.strategy_params["slow_period"] == 3


def test_create_with_multiple_tickers_dedupes_and_sorts(
    db_session: Session,
) -> None:
    _add_asset(db_session, "MSFT")
    _add_asset(db_session, "AAPL")
    bot = _create(db_session, tickers=["MSFT", "AAPL", "msft"])

    assert [s.ticker for s in bot.symbols] == ["AAPL", "MSFT"]


def test_create_whole_universe_resolves_eligible_equities(
    db_session: Session,
) -> None:
    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "MSFT")
    _add_asset(db_session, "PENNY", is_eligible=False)
    _add_asset(db_session, "BTC", category="crypto")

    bot = _create(db_session, tickers=None, whole_universe=True)

    # Only eligible equities; ineligible + crypto excluded.
    assert {s.ticker for s in bot.symbols} == {"AAPL", "MSFT"}


def test_create_whole_universe_empty_rejected(db_session: Session) -> None:
    _add_asset(db_session, "BTC", category="crypto")  # no eligible equities
    with pytest.raises(InvalidBotConfigError):
        _create(db_session, tickers=None, whole_universe=True)


def test_create_empty_ticker_set_rejected(db_session: Session) -> None:
    with pytest.raises(InvalidBotConfigError):
        _create(db_session, tickers=[])


def test_create_rejects_unknown_sizing_method(db_session: Session) -> None:
    _add_asset(db_session)
    with pytest.raises(InvalidBotConfigError):
        _create(db_session, sizing_method="moon_math")


def test_create_rejects_unknown_strategy(db_session: Session) -> None:
    _add_asset(db_session)
    with pytest.raises(UnknownStrategyError):
        _create(db_session, strategy_key="not_a_strategy")


def test_create_rsi_mean_reversion_session(db_session: Session) -> None:
    """A session with the RSI strategy and valid params persists end-to-end."""
    _add_asset(db_session)
    bot = _create(
        db_session,
        strategy_key="rsi_mean_reversion",
        strategy_params={"period": 14, "oversold": 30.0, "exit_level": 50.0},
    )

    assert bot.id is not None
    assert bot.strategy_key == "rsi_mean_reversion"
    assert bot.strategy_params["period"] == 14
    assert bot.status == "active"


def test_create_rejects_unknown_benchmark(db_session: Session) -> None:
    _add_asset(db_session)
    with pytest.raises(InvalidBotBenchmarkError):
        _create(db_session, benchmark="NOT_A_BENCHMARK")


def test_create_rejects_non_universe_ticker(db_session: Session) -> None:
    with pytest.raises(IneligibleAssetError):
        _create(db_session, tickers=["ZZZZ"])


def test_create_rejects_non_equity_asset(db_session: Session) -> None:
    _add_asset(db_session, ticker="BTC", category="crypto")
    with pytest.raises(IneligibleAssetError):
        _create(db_session, tickers=["BTC"])


def test_create_rejects_ineligible_asset(db_session: Session) -> None:
    _add_asset(db_session, ticker="PENNY", is_eligible=False)
    with pytest.raises(IneligibleAssetError):
        _create(db_session, tickers=["PENNY"])


def test_stop_then_archive_transitions(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    service.stop_bot_session(db_session, bot.id)
    assert bot.status == "stopped"

    service.archive_bot_session(db_session, bot.id)
    assert bot.status == "archived"
    assert bot.archived_at is not None


def test_archive_requires_stopped(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    with pytest.raises(BotSessionNotArchivableError):
        service.archive_bot_session(db_session, bot.id)


def test_list_hides_archived_by_default(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.stop_bot_session(db_session, bot.id)
    service.archive_bot_session(db_session, bot.id)

    assert service.list_bot_sessions(db_session) == []
    assert len(service.list_bot_sessions(db_session, include_archived=True)) == 1


# Tick runner -------------------------------------------------------------
def _up_cross(price: float) -> list[float]:
    """A flat series that jumps to ``price`` → fast SMA crosses above slow."""
    return [price * 0.5, price * 0.5, price * 0.5, price * 0.5, price]


def test_tick_market_closed_is_noop(db_session: Session) -> None:
    _add_asset(db_session)
    _create(db_session)
    broker = _OpenableBroker(market_open=False)

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [10.0] * 4}),
        now=_NOW,
    )

    assert result.market_open is False
    assert result.processed == 0


def test_tick_only_advances_active_sessions(db_session: Session) -> None:
    _add_asset(db_session)
    active = _create(db_session)
    stopped = _create(db_session)
    service.stop_bot_session(db_session, stopped.id)
    broker = _OpenableBroker()

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [10.0, 10.0, 10.0, 10.0]}),
        now=_NOW,
    )

    assert result.processed == 1
    assert active.total_trades == 0


def test_tick_enters_on_up_cross_within_budget(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    broker = _OpenableBroker()
    price = broker.get_quote("AAPL").last
    assert price is not None

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": _up_cross(price)}),
        now=_NOW,
    )

    assert result.processed == 1
    assert len(bot.positions) == 1
    assert bot.positions[0].quantity > 0
    assert bot.total_trades == 1
    # Budget ceiling: deployed cost never exceeds the initial capital.
    deployed = sum(p.quantity * p.avg_price for p in bot.positions)
    assert deployed <= bot.initial_capital


def test_tick_enforces_max_positions(db_session: Session) -> None:
    for ticker in ("AAA", "BBB", "CCC"):
        _add_asset(db_session, ticker)
    bot = _create(
        db_session,
        tickers=["AAA", "BBB", "CCC"],
        max_positions=2,
        max_position_pct=0.2,
    )
    broker = _OpenableBroker()
    series = {
        t: _up_cross(broker.get_quote(t).last or 0.0)
        for t in ("AAA", "BBB", "CCC")
    }

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData(series),
        now=_NOW,
    )

    # Only two names funded despite three signalling; ascending ticker wins.
    assert len(bot.positions) == 2
    assert sorted(p.ticker for p in bot.positions) == ["AAA", "BBB"]


def test_tick_budget_ceiling_across_many_signals(db_session: Session) -> None:
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    for ticker in tickers:
        _add_asset(db_session, ticker)
    bot = _create(
        db_session,
        tickers=tickers,
        initial_capital=1_000.0,
        max_positions=10,
        max_position_pct=1.0,
        cash_buffer_pct=0.0,
    )
    broker = _OpenableBroker()
    series = {t: _up_cross(broker.get_quote(t).last or 0.0) for t in tickers}

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData(series),
        now=_NOW,
    )

    deployed = sum(p.quantity * p.avg_price for p in bot.positions)
    assert deployed <= 1_000.0
    assert bot.cash >= 0.0


def test_tick_take_profit_exits_before_entries(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    bot = _create(db_session, take_profit_pct=0.05, drawdown_stop_pct=0.99)
    broker = _OpenableBroker()
    price = broker.get_quote("AAPL").last
    assert price is not None
    # Register the holding with the broker so the exit sell can fill, then seed
    # the matching ORM position bought cheaply so the current price triggers TP.
    broker.buy(symbol="AAPL", quantity=10.0)
    bot.positions.append(
        BotPosition(
            asset_id=bot.symbols[0].asset_id,
            ticker="AAPL",
            alpaca_symbol="AAPL",
            quantity=10.0,
            avg_price=price * 0.5,
            opened_at=_NOW,
        )
    )
    bot.cash = bot.initial_capital - 10.0 * price * 0.5
    db_session.flush()

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [price] * 5}),
        now=_NOW,
    )

    # Take-profit sold the position; no re-entry on a flat/no-cross series.
    assert bot.is_flat
    assert any(t.reason == "take_profit" for t in bot.trades)


def test_tick_drawdown_kill_switch_stops_session(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    bot = _create(db_session, drawdown_stop_pct=0.10)
    broker = _OpenableBroker()
    price = broker.get_quote("AAPL").last
    assert price is not None
    # Register the holding with the broker, then open a matching ORM position at a
    # high cost; peak reflects that. A big drop blows the drawdown floor.
    broker.buy(symbol="AAPL", quantity=100.0)
    bot.positions.append(
        BotPosition(
            asset_id=bot.symbols[0].asset_id,
            ticker="AAPL",
            alpaca_symbol="AAPL",
            quantity=100.0,
            avg_price=price,
            opened_at=_NOW,
        )
    )
    bot.cash = bot.initial_capital - 100.0 * price
    bot.peak_value = bot.initial_capital
    db_session.flush()

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [price * 0.5] * 5}),
        now=_NOW,
    )

    assert bot.status == "stopped"
    assert bot.is_flat
    assert bot.trades[-1].reason == "drawdown_kill_switch"


def test_tick_skips_session_when_all_data_stale(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    broker = _OpenableBroker()

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [10.0] * 4}, fresh=False),
        now=_NOW,
    )

    assert result.skipped == 1
    assert result.processed == 0
    assert bot.is_flat
    assert bot.total_trades == 0


# Snapshots & KPIs --------------------------------------------------------
def _add_position(
    db_session: Session, bot: BotSession, ticker: str, qty: float, avg: float
) -> None:
    asset = next(s for s in bot.symbols if s.ticker == ticker)
    bot.positions.append(
        BotPosition(
            asset_id=asset.asset_id,
            ticker=ticker,
            alpaca_symbol=asset.alpaca_symbol,
            quantity=qty,
            avg_price=avg,
            opened_at=_NOW,
        )
    )
    bot.cash -= qty * avg
    db_session.flush()


def test_record_snapshot_and_upsert(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    when = date(2026, 1, 5)

    snap = service.record_bot_snapshot(db_session, bot, marks={}, snapshot_date=when)
    assert snap.total_value == 100_000.0  # flat: cash only
    assert snap.unrealised_pnl == 0.0

    again = service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=when
    )
    assert again.id == snap.id
    assert len(service.list_bot_snapshots(db_session, bot)) == 1


def test_snapshot_marks_multiple_positions_to_market(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "MSFT")
    bot = _create(db_session, tickers=["AAPL", "MSFT"])
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    _add_position(db_session, bot, "MSFT", qty=50.0, avg=20.0)

    snap = service.record_bot_snapshot(
        db_session,
        bot,
        marks={"AAPL": 60.0, "MSFT": 15.0},
        snapshot_date=date(2026, 1, 6),
    )
    # 100*(60-50) + 50*(15-20) = 1000 - 250 = 750 unrealised.
    assert snap.unrealised_pnl == pytest.approx(750.0)
    # cash + 100*60 + 50*15 ; cash = 100k - 100*50 - 50*20 = 94000.
    assert snap.total_value == pytest.approx(94_000.0 + 6_000.0 + 750.0)


def test_kpis_from_snapshots(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 1, 5)
    )
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    service.record_bot_snapshot(
        db_session, bot, marks={"AAPL": 60.0}, snapshot_date=date(2026, 1, 6)
    )

    kpis = service.bot_session_kpis(db_session, bot)
    # cash = 95000; value = 95000 + 100*60 = 101000.
    assert kpis.current_value == pytest.approx(101_000.0)
    assert kpis.unrealised_pnl == pytest.approx(1000.0)
    assert kpis.total_return == pytest.approx(1000.0)
    assert kpis.total_return_pct == pytest.approx(0.01)


def test_kpis_without_snapshots_fall_back_to_cash(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    kpis = service.bot_session_kpis(db_session, bot)
    assert kpis.current_value == 100_000.0
    assert kpis.total_return == 0.0
    assert kpis.max_drawdown == 0.0
    assert kpis.sharpe_ratio is None


def test_kpis_include_available_cash(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)

    kpis = service.bot_session_kpis(db_session, bot)
    # Buying 100 @ 50 leaves 100000 - 5000 = 95000 free cash.
    assert kpis.cash == pytest.approx(95_000.0)
    assert kpis.cash == bot.cash


def test_kpis_include_benchmark_and_excess_return(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    start = date(2026, 1, 5)
    service.record_bot_snapshot(db_session, bot, marks={}, snapshot_date=start)
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    service.record_bot_snapshot(
        db_session, bot, marks={"AAPL": 60.0}, snapshot_date=date(2026, 1, 6)
    )
    # Benchmark +10% from the first snapshot date (anchor) to today (as_of).
    today = datetime.now(UTC).date()
    for on, close in ((start, 100.0), (today, 110.0)):
        db_session.add(
            BenchmarkPrice(
                benchmark=Benchmark.SP500.value, price_date=on, close=close
            )
        )
    db_session.flush()

    kpis = service.bot_session_kpis(db_session, bot)
    assert kpis.benchmark == "SP500"
    assert kpis.benchmark_return_pct == pytest.approx(0.10)
    # Excess is the session's own total return minus the benchmark's return.
    assert kpis.excess_return_pct == pytest.approx(kpis.total_return_pct - 0.10)


def test_kpis_benchmark_absent_without_snapshots(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    kpis = service.bot_session_kpis(db_session, bot)
    assert kpis.benchmark == "SP500"
    assert kpis.benchmark_return_pct is None
    assert kpis.excess_return_pct is None


def test_bot_current_value_uses_latest_snapshot(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    service.record_bot_snapshot(
        db_session, bot, marks={"AAPL": 60.0}, snapshot_date=date(2026, 1, 6)
    )

    # cash 95000 + 100 * 60 = 101000, from the marked snapshot.
    assert service.bot_current_value(db_session, bot) == pytest.approx(101_000.0)


def test_bot_current_value_falls_back_to_cost_without_snapshot(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)

    # No snapshot: cash 95000 + 100 * 50 (cost) = 100000.
    assert service.bot_current_value(db_session, bot) == pytest.approx(100_000.0)


def _add_value_point_full(
    db_session: Session,
    bot: BotSession,
    *,
    when: datetime,
    value: float,
    unrealised: float,
) -> None:
    db_session.add(
        BotValuePoint(
            session=bot,
            captured_at=when,
            total_value=value,
            realised_pnl=0.0,
            unrealised_pnl=unrealised,
        )
    )
    db_session.flush()


def test_latest_value_observation_prefers_newer_intraday_point(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 1, 6)
    )
    # A value point captured after the snapshot's created_at (≈ now) is the freshest.
    future = datetime.now(UTC) + timedelta(hours=1)
    _add_value_point_full(
        db_session, bot, when=future, value=102_000.0, unrealised=1_500.0
    )

    obs = service.latest_value_observation(db_session, bot)
    assert obs is not None
    assert obs.is_intraday is True
    assert obs.total_value == pytest.approx(102_000.0)
    assert obs.unrealised_pnl == pytest.approx(1_500.0)
    assert obs.as_of == future


def test_latest_value_observation_prefers_snapshot_when_newer(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    service.record_bot_snapshot(
        db_session, bot, marks={"AAPL": 60.0}, snapshot_date=date(2026, 1, 6)
    )
    # A stale intraday point from yesterday loses to the just-written snapshot.
    stale = datetime.now(UTC) - timedelta(days=1)
    _add_value_point_full(
        db_session, bot, when=stale, value=99_000.0, unrealised=-100.0
    )

    obs = service.latest_value_observation(db_session, bot)
    assert obs is not None
    assert obs.is_intraday is False
    assert obs.total_value == pytest.approx(101_000.0)
    assert obs.unrealised_pnl == pytest.approx(1_000.0)


def test_latest_value_observation_none_without_any_data(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    assert service.latest_value_observation(db_session, bot) is None


def test_bot_current_value_prefers_newer_intraday_point(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 1, 6)
    )
    future = datetime.now(UTC) + timedelta(hours=1)
    _add_value_point_full(
        db_session, bot, when=future, value=103_000.0, unrealised=0.0
    )

    assert service.bot_current_value(db_session, bot) == pytest.approx(103_000.0)


def test_bot_eod_value_is_latest_snapshot_or_none(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    assert service.bot_eod_value(db_session, bot) is None

    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    service.record_bot_snapshot(
        db_session, bot, marks={"AAPL": 60.0}, snapshot_date=date(2026, 1, 6)
    )
    # Latest snapshot total: cash 95000 + 100 * 60 = 101000, even if a newer
    # intraday point exists (eod value is the snapshot specifically).
    _add_value_point_full(
        db_session,
        bot,
        when=datetime.now(UTC) + timedelta(hours=1),
        value=102_000.0,
        unrealised=1_500.0,
    )
    assert service.bot_eod_value(db_session, bot) == pytest.approx(101_000.0)


def test_kpis_prefer_newer_intraday_point_and_expose_eod_value(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    service.record_bot_snapshot(
        db_session, bot, marks={"AAPL": 60.0}, snapshot_date=date(2026, 1, 6)
    )
    future = datetime.now(UTC) + timedelta(hours=1)
    _add_value_point_full(
        db_session, bot, when=future, value=102_000.0, unrealised=1_500.0
    )

    kpis = service.bot_session_kpis(db_session, bot)
    # Current value / unrealised come from the fresher intraday point…
    assert kpis.current_value == pytest.approx(102_000.0)
    assert kpis.unrealised_pnl == pytest.approx(1_500.0)
    assert kpis.value_is_intraday is True
    assert kpis.value_as_of == future
    assert kpis.total_return == pytest.approx(2_000.0)
    # …while the end-of-day value stays pinned to the latest daily snapshot.
    assert kpis.eod_value == pytest.approx(101_000.0)


def test_kpis_without_observation_mark_at_cost(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)

    kpis = service.bot_session_kpis(db_session, bot)
    # No snapshot and no value point: cost-marked, no freshness, no eod value.
    assert kpis.current_value == pytest.approx(100_000.0)
    assert kpis.unrealised_pnl == 0.0
    assert kpis.value_as_of is None
    assert kpis.value_is_intraday is False
    assert kpis.eod_value is None


# Trades-on-day count (Task 2.1) -----------------------------------------
def _add_trade(
    db_session: Session, bot: BotSession, *, when: datetime, ticker: str = "AAPL"
) -> None:
    db_session.add(
        BotTrade(
            bot_session_id=bot.id,
            side=OrderSide.BUY.value,
            ticker=ticker,
            quantity=1.0,
            filled_price=10.0,
            fees=0.0,
            created_at=when,
        )
    )
    db_session.flush()


def test_count_bot_trades_on_only_counts_the_day(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    day = date(2026, 1, 6)
    _add_trade(db_session, bot, when=datetime(2026, 1, 6, 0, 0, tzinfo=UTC))
    _add_trade(db_session, bot, when=datetime(2026, 1, 6, 23, 59, tzinfo=UTC))
    _add_trade(db_session, bot, when=datetime(2026, 1, 5, 23, 59, tzinfo=UTC))
    _add_trade(db_session, bot, when=datetime(2026, 1, 7, 0, 1, tzinfo=UTC))

    assert service.count_bot_trades_on(db_session, bot, day) == 2


# Paginated trade ledger -------------------------------------------------
def test_list_bot_trades_page_windows_and_totals(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    # Five trades at increasing times → most-recent-first is t5..t1.
    for minute in range(5):
        _add_trade(
            db_session, bot, when=datetime(2026, 1, 6, 9, minute, tzinfo=UTC)
        )

    first, total = service.list_bot_trades_page(db_session, bot, limit=2, offset=0)
    assert total == 5
    assert len(first) == 2
    # Most-recent-first: the two latest timestamps.
    assert [t.created_at.minute for t in first] == [4, 3]

    second, total2 = service.list_bot_trades_page(db_session, bot, limit=2, offset=2)
    assert total2 == 5
    assert [t.created_at.minute for t in second] == [2, 1]

    last, _ = service.list_bot_trades_page(db_session, bot, limit=2, offset=4)
    assert [t.created_at.minute for t in last] == [0]


# Best/worst closed round-trip ------------------------------------------
def _add_fill(
    db_session: Session,
    bot: BotSession,
    *,
    side: OrderSide,
    ticker: str,
    qty: float,
    price: float,
    when: datetime,
    fees: float = 0.0,
) -> None:
    db_session.add(
        BotTrade(
            bot_session_id=bot.id,
            side=side.value,
            ticker=ticker,
            quantity=qty,
            filled_price=price,
            fees=fees,
            created_at=when,
        )
    )
    db_session.flush()


def test_trade_extremes_none_without_closed_round_trip(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    # An open buy with no matching sell yet → no closed round-trip.
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="AAPL", qty=10.0, price=50.0,
        when=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
    )

    best, worst = service.bot_trade_extremes(db_session, bot)
    assert best is None
    assert worst is None
    kpis = service.bot_session_kpis(db_session, bot)
    assert kpis.best_trade is None
    assert kpis.worst_trade is None


def test_trade_extremes_single_round_trip_is_best_and_worst(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="AAPL", qty=10.0, price=50.0,
        when=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="AAPL", qty=10.0, price=55.0,
        when=datetime(2026, 1, 7, 9, 0, tzinfo=UTC),
    )

    best, worst = service.bot_trade_extremes(db_session, bot)
    # (55 - 50) * 10 = 50 realized; the lone round-trip is both best and worst.
    assert best is not None and worst is not None
    assert best.ticker == "AAPL"
    assert best.realised_pnl == pytest.approx(50.0)
    assert worst.realised_pnl == pytest.approx(50.0)


def test_trade_extremes_picks_max_and_min_across_tickers(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    # AAPL: +100 winner. MSFT: -60 loser. Fees reduce each round-trip's P&L.
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="AAPL", qty=10.0, price=50.0,
        when=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="AAPL", qty=10.0, price=60.0,
        when=datetime(2026, 1, 7, 9, 0, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="MSFT", qty=5.0, price=100.0,
        when=datetime(2026, 1, 6, 9, 5, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="MSFT", qty=5.0, price=88.0,
        when=datetime(2026, 1, 7, 9, 5, tzinfo=UTC),
    )

    best, worst = service.bot_trade_extremes(db_session, bot)
    assert best is not None and worst is not None
    assert best.ticker == "AAPL"
    assert best.realised_pnl == pytest.approx(100.0)  # (60-50)*10
    assert worst.ticker == "MSFT"
    assert worst.realised_pnl == pytest.approx(-60.0)  # (88-100)*5

    kpis = service.bot_session_kpis(db_session, bot)
    assert kpis.best_trade is not None and kpis.best_trade.ticker == "AAPL"
    assert kpis.worst_trade is not None and kpis.worst_trade.ticker == "MSFT"


def test_trade_extremes_nets_entry_and_exit_fees(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="AAPL", qty=10.0, price=50.0,
        when=datetime(2026, 1, 6, 9, 0, tzinfo=UTC), fees=2.0,
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="AAPL", qty=10.0, price=55.0,
        when=datetime(2026, 1, 7, 9, 0, tzinfo=UTC), fees=3.0,
    )

    best, _ = service.bot_trade_extremes(db_session, bot)
    # (55 - 50) * 10 - 2 - 3 = 45 net of both fills' fees.
    assert best is not None
    assert best.realised_pnl == pytest.approx(45.0)


def test_list_bot_trades_page_empty_session(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    items, total = service.list_bot_trades_page(db_session, bot, limit=20, offset=0)
    assert items == []
    assert total == 0


# Daily P&L vs prior snapshot (Task 2.2) ---------------------------------
def test_bot_daily_pnl_diffs_prior_snapshot(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 1, 5)
    )
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    today = service.record_bot_snapshot(
        db_session, bot, marks={"AAPL": 60.0}, snapshot_date=date(2026, 1, 6)
    )

    prior = service.get_previous_bot_value_snapshot(
        db_session, session_id=bot.id, before=date(2026, 1, 6)
    )
    assert prior is not None and prior.snapshot_date == date(2026, 1, 5)
    pnl, pct = service.bot_daily_pnl(db_session, bot, today)
    # value today 101000 vs prior 100000.
    assert pnl == pytest.approx(1_000.0)
    assert pct == pytest.approx(0.01)


def test_bot_daily_pnl_day_one_uses_allocated_capital(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    snap = service.record_bot_snapshot(
        db_session, bot, marks={"AAPL": 60.0}, snapshot_date=date(2026, 1, 6)
    )

    pnl, pct = service.bot_daily_pnl(db_session, bot, snap)
    # No prior snapshot: baseline is allocated capital (100000).
    assert pnl == pytest.approx(1_000.0)
    assert pct == pytest.approx(0.01)


def test_bot_daily_pnl_guards_non_positive_baseline(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    db_session.add(
        BotValueSnapshot(
            session=bot,
            snapshot_date=date(2026, 1, 5),
            total_value=0.0,
            realised_pnl=0.0,
            unrealised_pnl=0.0,
        )
    )
    db_session.flush()
    today = service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 1, 6)
    )

    pnl, pct = service.bot_daily_pnl(db_session, bot, today)
    assert pnl == pytest.approx(100_000.0)
    assert pct is None  # baseline 0 → percent omitted


# Bot Sharpe from the snapshot series (Task 2.3) -------------------------
def _seed_snapshots(
    db_session: Session, bot: BotSession, values: list[float]
) -> None:
    base = date(2026, 1, 1)
    for i, value in enumerate(values):
        db_session.add(
            BotValueSnapshot(
                session=bot,
                snapshot_date=base + timedelta(days=i),
                total_value=value,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            )
        )
    db_session.flush()


def test_sharpe_none_below_min_history(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    # A handful of varying snapshots — fewer than the 20-observation minimum.
    _seed_snapshots(db_session, bot, [100_000.0 + i * 100 for i in range(5)])

    assert service.bot_session_kpis(db_session, bot).sharpe_ratio is None


def test_sharpe_finite_with_enough_history(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    # 25 snapshots → 24 returns (> 20) with non-zero variance.
    values = [100_000.0 * (1.01 if i % 2 else 1.02) ** i for i in range(25)]
    _seed_snapshots(db_session, bot, values)

    sharpe = service.bot_session_kpis(db_session, bot).sharpe_ratio
    assert sharpe is not None
    assert isinstance(sharpe, float)


# Kill-switch notification (Tasks 3.1 / 3.2) -----------------------------
def _arm_drawdown(db_session: Session, bot: BotSession, broker: _OpenableBroker) -> float:
    """Open a high-cost position so a halving tick blows the drawdown floor."""
    price = broker.get_quote("AAPL").last
    assert price is not None
    broker.buy(symbol="AAPL", quantity=100.0)
    bot.positions.append(
        BotPosition(
            asset_id=bot.symbols[0].asset_id,
            ticker="AAPL",
            alpaca_symbol="AAPL",
            quantity=100.0,
            avg_price=price,
            opened_at=_NOW,
        )
    )
    bot.cash = bot.initial_capital - 100.0 * price
    bot.peak_value = bot.initial_capital
    db_session.flush()
    return price


def test_kill_switch_sends_one_push(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    bot = _create(db_session, drawdown_stop_pct=0.10)
    broker = _OpenableBroker()
    price = _arm_drawdown(db_session, bot, broker)
    notifier = RecordingNotifier()

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [price * 0.5] * 5}),
        now=_NOW,
        notifier=notifier,
    )

    assert bot.status == "stopped"
    assert len(notifier.sent) == 1
    message, title = notifier.sent[0]
    assert "drawdown kill-switch" in title
    assert "Liquidated 1 position(s): AAPL" in message
    assert "Bot is now stopped." in message


def test_no_kill_switch_sends_no_push(db_session: Session) -> None:
    _add_asset(db_session)
    _create(db_session)
    broker = _OpenableBroker()
    notifier = RecordingNotifier()

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [10.0, 10.0, 10.0, 10.0]}),
        now=_NOW,
        notifier=notifier,
    )

    assert notifier.sent == []


def test_kill_switch_raising_notifier_still_stops(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    bot = _create(db_session, drawdown_stop_pct=0.10)
    broker = _OpenableBroker()
    price = _arm_drawdown(db_session, bot, broker)

    # A raising notifier and a None notifier both leave the session stopped+flat.
    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [price * 0.5] * 5}),
        now=_NOW,
        notifier=RecordingNotifier(raises=True),
    )

    assert bot.status == "stopped"
    assert bot.is_flat


# Evening summary notification (Tasks 4.1 / 4.2) -------------------------
def test_snapshot_job_sends_one_summary_per_bot(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    bot = _create(db_session, tickers=["AAPL"])
    _add_position(db_session, bot, "AAPL", qty=100.0, avg=50.0)
    # Yesterday's snapshot so the summary can diff a prior value.
    db_session.add(
        BotValueSnapshot(
            session=bot,
            snapshot_date=date(2026, 1, 5),
            total_value=100_000.0,
            realised_pnl=0.0,
            unrealised_pnl=0.0,
        )
    )
    # Two trades today, one on an earlier day (must be excluded from the count).
    _add_trade(db_session, bot, when=datetime(2026, 1, 6, 10, 0, tzinfo=UTC))
    _add_trade(db_session, bot, when=datetime(2026, 1, 6, 11, 0, tzinfo=UTC))
    _add_trade(db_session, bot, when=datetime(2026, 1, 4, 11, 0, tzinfo=UTC))

    broker = _OpenableBroker()
    notifier = RecordingNotifier()
    service.run_bot_snapshots(
        db_session,
        broker=broker,
        now=datetime(2026, 1, 6, 21, 0, tzinfo=UTC),
        notifier=notifier,
    )

    assert len(notifier.sent) == 1
    message, title = notifier.sent[0]
    assert "daily P&L" in title
    assert "Total return:" in message
    assert "Trades today: 2" in message


def test_snapshot_job_raising_notifier_still_records(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    broker = _OpenableBroker()

    result = service.run_bot_snapshots(
        db_session,
        broker=broker,
        now=datetime(2026, 1, 6, 21, 0, tzinfo=UTC),
        notifier=RecordingNotifier(raises=True),
    )

    assert result.snapshots == 1
    assert len(service.list_bot_snapshots(db_session, bot)) == 1


# Multi-resolution value history -----------------------------------------
def _add_value_point(
    db_session: Session, bot: BotSession, *, when: datetime, value: float
) -> None:
    db_session.add(
        BotValuePoint(
            session=bot,
            captured_at=when,
            total_value=value,
            realised_pnl=0.0,
            unrealised_pnl=0.0,
        )
    )
    db_session.flush()


def test_value_history_5min_is_raw_points_oldest_first(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    # Insert out of order to prove the query orders ascending by capture time.
    _add_value_point(db_session, bot, when=datetime(2026, 1, 6, 15, 5, tzinfo=UTC), value=102.0)
    _add_value_point(db_session, bot, when=datetime(2026, 1, 6, 15, 0, tzinfo=UTC), value=100.0)
    _add_value_point(db_session, bot, when=datetime(2026, 1, 6, 15, 10, tzinfo=UTC), value=101.0)

    points = service.list_bot_value_history(
        db_session, bot, resolution=BotValueResolution.FIVE_MIN
    )
    assert [p.total_value for p in points] == [100.0, 102.0, 101.0]
    assert [p.timestamp.minute for p in points] == [0, 5, 10]


def test_value_history_hourly_keeps_last_point_per_hour(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_value_point(db_session, bot, when=datetime(2026, 1, 6, 15, 0, tzinfo=UTC), value=100.0)
    _add_value_point(db_session, bot, when=datetime(2026, 1, 6, 15, 55, tzinfo=UTC), value=105.0)
    _add_value_point(db_session, bot, when=datetime(2026, 1, 6, 16, 10, tzinfo=UTC), value=110.0)

    points = service.list_bot_value_history(
        db_session, bot, resolution=BotValueResolution.HOURLY
    )
    # One point per clock hour: the last of 15:00/15:55, then 16:10.
    assert [p.total_value for p in points] == [105.0, 110.0]
    assert [(p.timestamp.hour, p.timestamp.minute) for p in points] == [(15, 55), (16, 10)]


def test_value_history_daily_maps_snapshots_to_end_of_day(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    _seed_snapshots(db_session, bot, [100.0, 101.0, 102.0])

    points = service.list_bot_value_history(
        db_session, bot, resolution=BotValueResolution.DAILY
    )
    assert [p.total_value for p in points] == [100.0, 101.0, 102.0]
    assert points[0].timestamp == datetime(2026, 1, 1, 23, 59, 59, tzinfo=UTC)


def test_value_history_monthly_keeps_last_snapshot_per_month(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    for d, value in [
        (date(2026, 1, 10), 100.0),
        (date(2026, 1, 31), 110.0),
        (date(2026, 2, 15), 120.0),
    ]:
        db_session.add(
            BotValueSnapshot(
                session=bot,
                snapshot_date=d,
                total_value=value,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            )
        )
    db_session.flush()

    points = service.list_bot_value_history(
        db_session, bot, resolution=BotValueResolution.MONTHLY
    )
    # Last snapshot of January, then February.
    assert [p.total_value for p in points] == [110.0, 120.0]
    assert [p.timestamp.month for p in points] == [1, 2]


def test_value_history_empty_series_per_resolution(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    for resolution in BotValueResolution:
        assert service.list_bot_value_history(
            db_session, bot, resolution=resolution
        ) == []


def test_tick_persists_one_value_point_per_processed_session(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    broker = _OpenableBroker()
    price = broker.get_quote("AAPL").last
    assert price is not None

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": _up_cross(price)}),
        now=_NOW,
    )

    points = service.list_bot_value_history(
        db_session, bot, resolution=BotValueResolution.FIVE_MIN
    )
    assert len(points) == 1
    assert points[0].timestamp == _NOW
    # Total value after the entry = cash + marked position; a flat mark to cost
    # leaves total at the initial capital.
    assert points[0].total_value == pytest.approx(bot.initial_capital)


def test_tick_market_closed_persists_no_value_point(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    service.run_tick(
        db_session,
        broker=_OpenableBroker(market_open=False),
        market_data=_PerSymbolMarketData({"AAPL": [10.0] * 4}),
        now=_NOW,
    )

    assert (
        service.list_bot_value_history(
            db_session, bot, resolution=BotValueResolution.FIVE_MIN
        )
        == []
    )


def test_snapshot_job_prunes_value_points_past_retention(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    now = datetime(2026, 3, 1, 21, 0, tzinfo=UTC)
    retention = settings.BOT_VALUE_POINT_RETENTION_DAYS
    # One point well inside the window, one just past it.
    _add_value_point(
        db_session, bot, when=now - timedelta(days=1), value=100.0
    )
    _add_value_point(
        db_session, bot, when=now - timedelta(days=retention + 1), value=90.0
    )
    # A daily snapshot predating the window must survive (snapshots are unbounded).
    _seed_snapshots(db_session, bot, [100.0])

    service.run_bot_snapshots(db_session, broker=_OpenableBroker(), now=now)

    kept = service.list_bot_value_history(
        db_session, bot, resolution=BotValueResolution.FIVE_MIN
    )
    assert [p.total_value for p in kept] == [100.0]
    # Daily history untouched by intraday pruning: the pre-window snapshot
    # survives (alongside the one this job run records).
    daily = service.list_bot_value_history(
        db_session, bot, resolution=BotValueResolution.DAILY
    )
    assert datetime(2026, 1, 1, 23, 59, 59, tzinfo=UTC) in [
        p.timestamp for p in daily
    ]


# Stop metadata ----------------------------------------------------------
def test_manual_stop_records_reason_and_timestamp(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    service.stop_bot_session(db_session, bot.id)

    assert bot.stop_reason == "manual"
    assert bot.stopped_at is not None


def test_kill_switch_records_reason_and_timestamp(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    bot = _create(db_session, drawdown_stop_pct=0.10)
    broker = _OpenableBroker()
    price = broker.get_quote("AAPL").last
    assert price is not None
    broker.buy(symbol="AAPL", quantity=100.0)
    bot.positions.append(
        BotPosition(
            asset_id=bot.symbols[0].asset_id,
            ticker="AAPL",
            alpaca_symbol="AAPL",
            quantity=100.0,
            avg_price=price,
            opened_at=_NOW,
        )
    )
    bot.cash = bot.initial_capital - 100.0 * price
    bot.peak_value = bot.initial_capital
    db_session.flush()

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": [price * 0.5] * 5}),
        now=_NOW,
    )

    assert bot.stop_reason == "drawdown_kill_switch"
    assert bot.stopped_at == _NOW


# Round-trip entry/exit detail + count/win-rate --------------------------
def test_trade_extremes_carry_entry_and_exit_detail(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    entry_at = datetime(2026, 1, 6, 9, 0, tzinfo=UTC)
    exit_at = datetime(2026, 1, 7, 9, 0, tzinfo=UTC)
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="AAPL", qty=10.0, price=50.0,
        when=entry_at,
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="AAPL", qty=10.0, price=55.0,
        when=exit_at,
    )

    best, _ = service.bot_trade_extremes(db_session, bot)
    assert best is not None
    assert best.quantity == pytest.approx(10.0)
    assert best.entry_price == pytest.approx(50.0)
    assert best.entry_at == entry_at
    assert best.exit_price == pytest.approx(55.0)
    assert best.exit_at == exit_at


def test_round_trips_count_and_win_rate_on_mixed_ledger(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    # One winner (AAPL +50) and one loser (MSFT -25) → two round-trips, 50% wins.
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="AAPL", qty=10.0, price=50.0,
        when=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="AAPL", qty=10.0, price=55.0,
        when=datetime(2026, 1, 7, 9, 0, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="MSFT", qty=5.0, price=100.0,
        when=datetime(2026, 1, 6, 9, 5, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="MSFT", qty=5.0, price=95.0,
        when=datetime(2026, 1, 7, 9, 5, tzinfo=UTC),
    )

    round_trips = service.bot_round_trips(db_session, bot)
    assert len(round_trips) == 2
    stats = service.bot_session_summary_stats(db_session, bot)
    assert stats.trade_count == 2
    assert stats.win_rate == pytest.approx(0.5)


# Summary stats assembly -------------------------------------------------
def test_summary_stats_assembles_fields(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    bot.created_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="AAPL", qty=10.0, price=50.0,
        when=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="AAPL", qty=10.0, price=60.0,
        when=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
    )
    bot.peak_value = 123_456.0
    service.stop_bot_session(db_session, bot.id)
    bot.stopped_at = datetime(2026, 1, 4, 12, 0, tzinfo=UTC)
    db_session.flush()

    stats = service.bot_session_summary_stats(db_session, bot)
    assert stats.stop_reason == "manual"
    assert stats.stopped_at == datetime(2026, 1, 4, 12, 0, tzinfo=UTC)
    assert stats.lifespan_days == 3  # Jan 1 → Jan 4
    assert stats.peak_value == pytest.approx(123_456.0)
    assert stats.trade_count == 1
    assert stats.win_rate == pytest.approx(1.0)
    assert stats.best_trade is not None
    assert stats.best_trade.realised_pnl == pytest.approx(100.0)
    assert stats.benchmark == "SP500"


def test_summary_stats_none_without_trades_or_benchmark_data(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.stop_bot_session(db_session, bot.id)

    stats = service.bot_session_summary_stats(db_session, bot)
    assert stats.trade_count == 0
    assert stats.win_rate is None
    assert stats.best_trade is None
    assert stats.worst_trade is None
    assert stats.benchmark_return_pct is None
    assert stats.excess_return_pct is None


# Summary fingerprint ----------------------------------------------------
def test_summary_fingerprint_is_stable_and_changes(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.stop_bot_session(db_session, bot.id)
    stats = service.bot_session_summary_stats(db_session, bot)

    first = service._summary_fingerprint(stats)
    assert first == service._summary_fingerprint(stats)

    changed = replace(stats, final_value=stats.final_value + 1_000.0)
    assert service._summary_fingerprint(changed) != first


# Cached AI summary ------------------------------------------------------
def _stopped_bot_with_round_trip(db_session: Session) -> BotSession:
    _add_asset(db_session)
    bot = _create(db_session)
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="AAPL", qty=10.0, price=50.0,
        when=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="AAPL", qty=10.0, price=55.0,
        when=datetime(2026, 1, 7, 9, 0, tzinfo=UTC),
    )
    service.stop_bot_session(db_session, bot.id)
    return bot


def test_summary_generates_then_caches(db_session: Session) -> None:
    bot = _stopped_bot_with_round_trip(db_session)
    agent = FakeBotSummaryAgent()

    first = service.bot_session_summary(db_session, bot, agent)
    assert agent.calls == 1
    assert first.narrative is not None
    assert "The session closed in the green." in first.narrative
    assert bot.summary_fingerprint is not None

    second = service.bot_session_summary(db_session, bot, agent)
    assert agent.calls == 1  # cache hit — agent not called again
    assert second.narrative == first.narrative


def test_summary_regenerates_on_fingerprint_change(db_session: Session) -> None:
    bot = _stopped_bot_with_round_trip(db_session)
    agent = FakeBotSummaryAgent()
    service.bot_session_summary(db_session, bot, agent)
    assert agent.calls == 1

    # A changed input (a new closed round-trip) shifts the fingerprint.
    _add_fill(
        db_session, bot, side=OrderSide.BUY, ticker="MSFT", qty=5.0, price=100.0,
        when=datetime(2026, 1, 8, 9, 0, tzinfo=UTC),
    )
    _add_fill(
        db_session, bot, side=OrderSide.SELL, ticker="MSFT", qty=5.0, price=110.0,
        when=datetime(2026, 1, 9, 9, 0, tzinfo=UTC),
    )

    service.bot_session_summary(db_session, bot, agent)
    assert agent.calls == 2  # regenerated


def test_summary_agent_failure_returns_none_narrative(db_session: Session) -> None:
    bot = _stopped_bot_with_round_trip(db_session)
    agent = FakeBotSummaryAgent(fail=True)

    summary = service.bot_session_summary(db_session, bot, agent)
    assert agent.calls == 1
    assert summary.narrative is None
    assert summary.stats.trade_count == 1  # stats still assembled
    assert bot.summary_narrative is None  # nothing persisted


def test_summary_active_bot_raises_without_calling_agent(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create(db_session)  # active
    agent = FakeBotSummaryAgent()

    with pytest.raises(BotSessionNotStoppedError):
        service.bot_session_summary(db_session, bot, agent)
    assert agent.calls == 0


# Presets ---------------------------------------------------------------------
def _create_from_preset(
    db_session: Session, preset_key: str, **overrides: object
) -> BotSession:
    kwargs: dict[str, object] = {
        "preset_key": preset_key,
        "tickers": ["AAPL"],
        "initial_capital": 100_000.0,
        "benchmark": "SP500",
    }
    kwargs.update(overrides)
    return service.create_bot_session(db_session, **kwargs)  # type: ignore[arg-type]


def test_create_from_preset_without_overrides_uses_preset(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create_from_preset(db_session, "rsi_mean_reversion_algo16")

    assert bot.strategy_key == "rsi_mean_reversion"
    assert bot.strategy_params == {"period": 14, "oversold": 30.0, "exit_level": 50.0}
    assert bot.take_profit_pct == 0.005
    assert bot.stop_loss_pct == 0.01
    assert bot.drawdown_stop_pct == 0.05
    assert bot.preset_key == "rsi_mean_reversion_algo16"
    assert bot.preset_customized is False
    assert bot.origin == "manual"


def test_create_from_preset_override_marks_customized(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create_from_preset(
        db_session,
        "ma_crossover_algo6",
        strategy_params={"fast_period": 7, "slow_period": 12},
    )

    assert bot.strategy_params["fast_period"] == 7
    # Unsupplied risk values still come from the preset.
    assert bot.take_profit_pct == 0.01
    assert bot.stop_loss_pct == 0.02
    assert bot.preset_customized is True


def test_create_from_preset_explicit_none_turns_take_profit_off(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create_from_preset(db_session, "ma_crossover_algo6", take_profit_pct=None)

    assert bot.take_profit_pct is None
    assert bot.stop_loss_pct == 0.02
    assert bot.preset_customized is True


def test_create_from_preset_risk_override_marks_customized(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    bot = _create_from_preset(
        db_session, "donchian_turtle_algo25", drawdown_stop_pct=0.10
    )

    assert bot.drawdown_stop_pct == 0.10
    assert bot.preset_customized is True


def test_create_from_preset_equal_values_not_customized(db_session: Session) -> None:
    """Supplied values equal to the preset (incl. a version-only Donchian dict that
    omits inactive-version fields, and percent->fraction float math) are not custom."""
    _add_asset(db_session)
    bot = _create_from_preset(
        db_session,
        "donchian_smart_range_algo8",
        strategy_key="donchian_breakout",
        strategy_params={
            "version": "locked",
            "channel_period": 20,
            "atr_padding_mult": 0.5,
        },
        take_profit_pct=0.5 / 100,
        stop_loss_pct=2 / 100,
        drawdown_stop_pct=5 / 100,
    )

    assert bot.preset_key == "donchian_smart_range_algo8"
    assert bot.preset_customized is False


def test_create_from_unknown_preset_rejected(db_session: Session) -> None:
    _add_asset(db_session)
    with pytest.raises(UnknownPresetError):
        _create_from_preset(db_session, "not_a_preset")


def test_create_from_preset_with_mismatched_strategy_rejected(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    with pytest.raises(InvalidBotConfigError):
        _create_from_preset(
            db_session, "ma_crossover_algo6", strategy_key="rsi_mean_reversion"
        )


def test_create_without_strategy_or_preset_rejected(db_session: Session) -> None:
    _add_asset(db_session)
    with pytest.raises(InvalidBotConfigError):
        service.create_bot_session(
            db_session,
            tickers=["AAPL"],
            initial_capital=100_000.0,
            benchmark="SP500",
        )


def test_create_without_preset_records_no_provenance(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)

    assert bot.preset_key is None
    assert bot.preset_customized is False
    assert bot.origin == "manual"
    # Unchanged legacy defaults: no TP/SL, configured drawdown.
    assert bot.take_profit_pct is None
    assert bot.stop_loss_pct is None
    assert bot.drawdown_stop_pct == settings.BOT_DRAWDOWN_STOP_PCT


def test_create_from_rolling_reversion_preset(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create_from_preset(db_session, "rolling_reversion_vwap_cross_algo39")

    assert bot.strategy_key == "rolling_average_reversion"
    assert bot.strategy_params["average_type"] == "vwap"
    assert bot.strategy_params["window"] == 60
    assert bot.strategy_params["entry_threshold"] == 0.0
    assert bot.strategy_params["exit_mode"] == "bracket"
    assert bot.take_profit_pct == 0.005
    assert bot.stop_loss_pct == 0.01
    assert bot.drawdown_stop_pct == 0.05
    assert bot.preset_customized is False


# Selling stop ----------------------------------------------------------------
def _stopped_bot_with_positions(
    db_session: Session, broker: StubBroker
) -> BotSession:
    """A stopped bot holding AAPL x10 and MSFT x5, also held on the stub broker."""
    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "MSFT")
    bot = _create(db_session, tickers=["AAPL", "MSFT"])
    _add_position(db_session, bot, "AAPL", 10, 100.0)
    _add_position(db_session, bot, "MSFT", 5, 200.0)
    broker.buy("AAPL", 10)
    broker.buy("MSFT", 5)
    service.stop_bot_session(db_session, bot.id)
    return bot


def _sells(db_session: Session, bot: BotSession) -> list[BotTrade]:
    return [
        t
        for t in db_session.query(BotTrade).filter(BotTrade.bot_session_id == bot.id)
        if t.side == "sell"
    ]


def test_orchestrator_stop_records_reason(db_session: Session) -> None:
    from cadence.strategy_bots.constants import StopReason

    _add_asset(db_session)
    bot = _create(db_session)

    service.stop_bot_session(db_session, bot.id, reason=StopReason.ORCHESTRATOR)

    assert bot.status == "stopped"
    assert bot.stop_reason == "orchestrator"
    assert bot.stopped_at is not None


def test_tick_flattens_a_stopped_session(db_session: Session) -> None:
    broker = _OpenableBroker()
    bot = _stopped_bot_with_positions(db_session, broker)

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({}),
        now=_NOW,
    )

    assert result.flattened == 2
    assert bot.positions == []
    assert bot.status == "stopped"
    sells = _sells(db_session, bot)
    assert {t.ticker for t in sells} == {"AAPL", "MSFT"}
    assert all(t.reason == "session_stopped" for t in sells)


def test_tick_flattens_an_archived_session_with_leftovers(db_session: Session) -> None:
    broker = _OpenableBroker()
    bot = _stopped_bot_with_positions(db_session, broker)
    service.archive_bot_session(db_session, bot.id)

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({}),
        now=_NOW,
    )

    assert bot.positions == []
    assert bot.status == "archived"


def test_no_flatten_while_market_closed(db_session: Session) -> None:
    broker = _OpenableBroker(market_open=False)
    bot = _stopped_bot_with_positions(db_session, broker)

    result = service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({}),
        now=_NOW,
    )

    assert result.flattened == 0
    assert len(bot.positions) == 2
    assert _sells(db_session, bot) == []


def test_stopped_session_never_opens_a_position(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session)
    service.stop_bot_session(db_session, bot.id)
    broker = _OpenableBroker()
    price = broker.get_quote("AAPL").last
    assert price is not None

    # Bars that would trigger an MA-crossover entry for an active session.
    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({"AAPL": _up_cross(price)}),
        now=_NOW,
    )

    assert bot.positions == []
    assert bot.total_trades == 0


def test_flatten_credits_cash_and_realises_pnl(db_session: Session) -> None:
    broker = _OpenableBroker()
    bot = _stopped_bot_with_positions(db_session, broker)
    cash_before = bot.cash

    service.run_tick(
        db_session,
        broker=broker,
        market_data=_PerSymbolMarketData({}),
        now=_NOW,
    )

    proceeds = sum(t.quantity * (t.filled_price or 0.0) for t in _sells(db_session, bot))
    assert bot.cash == pytest.approx(cash_before + proceeds)


def test_rejected_flatten_sell_is_retried_without_failing_the_tick(
    db_session: Session,
) -> None:
    """A leftover the broker cannot sell stays on the ledger for the next tick, and the
    other sessions are still processed."""
    _add_asset(db_session, "AAPL")
    stopped = _create(db_session)
    _add_position(db_session, stopped, "AAPL", 10, 100.0)  # not held on the broker
    service.stop_bot_session(db_session, stopped.id)
    _create(db_session)  # an active session that must still be ticked

    result = service.run_tick(
        db_session,
        broker=_OpenableBroker(),
        market_data=_PerSymbolMarketData({"AAPL": [10.0] * 4}),
        now=_NOW,
    )

    assert result.flattened == 0
    assert result.processed == 1
    assert len(stopped.positions) == 1


def test_create_records_orchestrator_origin(db_session: Session) -> None:
    from cadence.bot_orchestrator.models import BotOrchestrator
    from cadence.strategy_bots.constants import BotOrigin

    orchestrator = BotOrchestrator(
        label="Orch",
        capital=10_000.0,
        free_capital=10_000.0,
        max_parallel_bots=3,
        max_bot_share=0.5,
        max_tickers_per_bot=5,
        cadence="daily",
        model="gpt-5-mini",
        benchmark="SP500",
    )
    db_session.add(orchestrator)
    db_session.flush()
    _add_asset(db_session)

    bot = _create(
        db_session,
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )

    assert bot.origin == "orchestrator"
    assert bot.orchestrator_id == orchestrator.id
    assert bot.capital_returned_at is None


def test_orchestrator_bots_are_snapshotted_without_their_own_push(
    db_session: Session,
) -> None:
    from cadence.bot_orchestrator.models import BotOrchestrator
    from cadence.strategy_bots.constants import BotOrigin

    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "MSFT")
    orchestrator = BotOrchestrator(
        label="Core",
        capital=10_000.0,
        free_capital=7_000.0,
        max_parallel_bots=3,
        max_bot_share=0.5,
        max_tickers_per_bot=5,
        cadence="daily",
        model="gpt-5-mini",
        benchmark="SP500",
    )
    db_session.add(orchestrator)
    db_session.flush()
    manual = _create(db_session, tickers=["AAPL"])
    deployed = _create(
        db_session,
        tickers=["MSFT"],
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )
    notifier = RecordingNotifier()
    when = datetime(2026, 1, 6, 21, 0, tzinfo=UTC)

    result = service.run_bot_snapshots(
        db_session, broker=_OpenableBroker(), now=when, notifier=notifier
    )

    assert result.snapshots == 2
    snapped = {
        s.bot_session_id
        for s in db_session.query(BotValueSnapshot).filter(
            BotValueSnapshot.snapshot_date == when.date()
        )
    }
    assert snapped == {manual.id, deployed.id}
    # Only the manual bot pushes; the orchestrator bot is rolled up.
    assert len(notifier.sent) == 1
    assert "MSFT" not in notifier.sent[0][1]


# Display name ------------------------------------------------------------------
def test_display_name_uses_label_when_set(db_session: Session) -> None:
    _add_asset(db_session)
    bot = _create(db_session, label="My momentum bot")
    assert service.bot_display_name(bot) == "My momentum bot"


def test_display_name_uses_preset_then_ticker(db_session: Session) -> None:
    _add_asset(db_session, "MSFT")
    bot = _create(
        db_session,
        strategy_key=None,
        strategy_params=service.UNSET,
        preset_key="donchian_turtle_algo25",
        tickers=["MSFT"],
    )
    assert service.bot_display_name(bot) == "Turtle Breakout (Algo 25) · MSFT"


def test_display_name_falls_back_to_strategy_display_name(db_session: Session) -> None:
    _add_asset(db_session, "MSFT")
    bot = _create(
        db_session,
        strategy_key="donchian_breakout",
        strategy_params={"version": "turtle", "entry_period": 20, "exit_period": 10},
        tickers=["MSFT"],
    )
    assert service.bot_display_name(bot) == "Donchian Range Breakout · MSFT"


def test_display_name_counts_several_symbols(db_session: Session) -> None:
    for ticker in ("AAPL", "MSFT", "NVDA"):
        _add_asset(db_session, ticker)
    bot = _create(
        db_session,
        strategy_key=None,
        strategy_params=service.UNSET,
        preset_key="rsi_mean_reversion_algo16",
        tickers=["AAPL", "MSFT", "NVDA"],
    )
    assert service.bot_display_name(bot) == "RSI Mean Reversion (Algo 16) · 3 symbols"


def test_push_titles_use_the_display_name(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    bot = _create(
        db_session,
        strategy_key=None,
        strategy_params=service.UNSET,
        preset_key="ma_crossover_algo6",
    )
    notifier = RecordingNotifier()

    service.run_bot_snapshots(
        db_session,
        broker=_OpenableBroker(),
        now=datetime(2026, 1, 6, 21, 0, tzinfo=UTC),
        notifier=notifier,
    )

    assert notifier.sent[0][1] == "Cadence bot: MA Crossover (Algo 6) · AAPL daily P&L"
    assert service.bot_display_name(bot) in notifier.sent[0][1]


# Per-bot isolation (the 2026-11-10 incident) ------------------------------
class _RejectingBuyBroker(_OpenableBroker):
    """Open-market stub whose buys of one symbol are refused by the broker (403)."""

    def __init__(self, reject: str) -> None:
        super().__init__()
        self._reject = reject

    def buy(self, symbol, quantity, *args, **kwargs):  # type: ignore[no-untyped-def, override]
        from cadence.broker.base import OrderError

        if symbol == self._reject:
            raise OrderError("Alpaca API error: forbidden")
        return super().buy(symbol, quantity, *args, **kwargs)


def test_one_bots_rejection_does_not_fail_or_undo_the_tick(db_session: Session) -> None:
    broker = _RejectingBuyBroker(reject="NVDA")
    stopped = _stopped_bot_with_positions(db_session, broker)
    _add_asset(db_session, "NVDA")
    good = _create(db_session, tickers=["AAPL"])
    bad = _create(db_session, tickers=["NVDA"])
    aapl = broker.get_quote("AAPL").last
    nvda = broker.get_quote("NVDA").last
    assert aapl is not None and nvda is not None
    market = _PerSymbolMarketData({"AAPL": _up_cross(aapl), "NVDA": _up_cross(nvda)})

    result = service.run_tick(db_session, broker=broker, market_data=market, now=_NOW)

    assert (result.processed, result.failed, result.flattened) == (1, 1, 2)
    assert stopped.positions == []
    assert len(good.positions) == 1
    assert bad.positions == []


def test_flattened_positions_are_not_sold_again_next_tick(db_session: Session) -> None:
    broker = _RejectingBuyBroker(reject="NVDA")
    stopped = _stopped_bot_with_positions(db_session, broker)
    _add_asset(db_session, "NVDA")
    _create(db_session, tickers=["NVDA"])
    nvda = broker.get_quote("NVDA").last
    assert nvda is not None
    market = _PerSymbolMarketData({"NVDA": _up_cross(nvda)})

    service.run_tick(db_session, broker=broker, market_data=market, now=_NOW)
    second = service.run_tick(
        db_session, broker=broker, market_data=market, now=_NOW + timedelta(minutes=5)
    )

    assert second.flattened == 0
    assert len(_sells(db_session, stopped)) == 2
    # The account never went short on the stopped bot's symbols.
    assert all(p.quantity >= 0 for p in broker.get_positions())


def test_flatten_refuses_to_sell_shares_the_account_no_longer_holds(
    db_session: Session,
) -> None:
    broker = _OpenableBroker()
    stopped = _stopped_bot_with_positions(db_session, broker)
    # Someone sold the shares outside Cadence: the ledger still claims them.
    for position in broker.get_positions():
        broker.sell(position.symbol, position.quantity)

    result = service.run_tick(
        db_session, broker=broker, market_data=_PerSymbolMarketData({}), now=_NOW
    )

    assert (result.flattened, result.failed) == (0, 0)
    assert len(stopped.positions) == 2
    assert _sells(db_session, stopped) == []
    assert all(p.quantity >= 0 for p in broker.get_positions())


def test_tick_endpoint_reports_failed_bots(client, db_session: Session) -> None:  # type: ignore[no-untyped-def]
    from cadence.api.app import app
    from cadence.broker import get_broker
    from cadence.strategy_bots.market_data import get_market_data

    broker = _RejectingBuyBroker(reject="NVDA")
    _add_asset(db_session, "NVDA")
    _create(db_session, tickers=["NVDA"])
    nvda = broker.get_quote("NVDA").last
    assert nvda is not None
    app.dependency_overrides[get_broker] = lambda: broker
    app.dependency_overrides[get_market_data] = lambda: _PerSymbolMarketData(
        {"NVDA": _up_cross(nvda)}
    )
    settings_token = settings.REBALANCE_CRON_TOKEN or "test-token"
    original = settings.REBALANCE_CRON_TOKEN
    settings.REBALANCE_CRON_TOKEN = settings_token
    try:
        response = client.post(
            "/api/v1/bots/tick", headers={"X-Cron-Token": settings_token}
        )
    finally:
        settings.REBALANCE_CRON_TOKEN = original

    assert response.status_code == 200
    assert response.json()["failed"] == 1
