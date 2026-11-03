"""Unit tests for the strategy-bot session service, tick runner, and KPIs."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.broker.stub import StubBroker
from cadence.strategy_bots import service
from cadence.strategy_bots.errors import (
    BotSessionNotArchivableError,
    IneligibleAssetError,
    InvalidBotBenchmarkError,
    InvalidBotConfigError,
    UnknownStrategyError,
)
from cadence.strategy_bots.market_data import BarsResult
from cadence.strategy_bots.models import BotPosition, BotSession
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
