"""Unit tests for the strategy-bot session service, tick runner, and KPIs."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session
from tests.fakes import RecordingNotifier

from cadence.assets.models import Asset
from cadence.broker.models import OrderSide
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
from cadence.strategy_bots.models import (
    BotPosition,
    BotSession,
    BotTrade,
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
    pnl, pct = service._bot_daily_pnl(db_session, bot, today)
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

    pnl, pct = service._bot_daily_pnl(db_session, bot, snap)
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

    pnl, pct = service._bot_daily_pnl(db_session, bot, today)
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

    count = service.run_bot_snapshots(
        db_session,
        broker=broker,
        now=datetime(2026, 1, 6, 21, 0, tzinfo=UTC),
        notifier=RecordingNotifier(raises=True),
    )

    assert count == 1
    assert len(service.list_bot_snapshots(db_session, bot)) == 1
