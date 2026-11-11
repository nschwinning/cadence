"""Tests for the strategy-bot dashboard comparison seam (``kind='bot'`` rows)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.broker.stub import StubBroker
from cadence.dashboard import service as dashboard_service
from cadence.dashboard.constants import DashboardRange
from cadence.paper_trading import service as paper_trading_service
from cadence.paper_trading.constants import Benchmark, SessionStatus
from cadence.paper_trading.models import BenchmarkPrice
from cadence.portfolios import service as portfolios_service
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.models import BotValuePoint

_TODAY = date(2026, 6, 15)
_NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def _add_asset(db_session: Session, ticker: str = "AAPL") -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.flush()
    return asset


def _make_bot(db_session: Session) -> object:
    _add_asset(db_session)
    return bot_service.create_bot_session(
        db_session,
        strategy_key="ma_crossover",
        tickers=["AAPL"],
        initial_capital=100_000.0,
        benchmark="SP500",
        strategy_params={"fast_period": 2, "slow_period": 3},
    )


def _seed_benchmark(db_session: Session) -> None:
    for on, close in ((date(2026, 6, 10), 100.0), (_TODAY, 110.0)):
        db_session.add(
            BenchmarkPrice(benchmark=Benchmark.SP500.value, price_date=on, close=close)
        )
    db_session.flush()


def _add_value_point(
    db_session: Session,
    bot: object,
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


def test_dashboard_performance_uses_fresher_intraday_value(
    db_session: Session,
) -> None:
    # A daily snapshot (value 100k, unrealised 0) plus a newer intraday point
    # (value 105k, unrealised 5k): the row's live value comes from the point...
    bot = _make_bot(db_session)
    bot_service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 6, 10)
    )
    _add_value_point(
        db_session,
        bot,
        when=datetime.now(UTC) + timedelta(hours=1),
        value=105_000.0,
        unrealised=5_000.0,
    )

    perf = bot_service.dashboard_performance(
        db_session, bot, range_=DashboardRange.MAX, today=_TODAY
    )

    assert perf.current_value == pytest.approx(105_000.0)
    assert perf.unrealised_pnl == pytest.approx(5_000.0)
    # ...while the plotted series stays the end-of-day daily snapshot.
    assert [p.date for p in perf.points] == [date(2026, 6, 10)]
    assert perf.points[0].value == pytest.approx(100_000.0)


def test_dashboard_performance_value_fallbacks(db_session: Session) -> None:
    # Snapshot only (no newer point): the row reports the latest snapshot value.
    bot = _make_bot(db_session)
    bot_service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 6, 10)
    )
    perf = bot_service.dashboard_performance(
        db_session, bot, range_=DashboardRange.MAX, today=_TODAY
    )
    assert perf.current_value == pytest.approx(100_000.0)

    # Neither snapshot nor point: cost-marked value with a zero unrealised baseline.
    # Reuse the already-inserted AAPL asset — a second bot, no new snapshot/point.
    fresh = bot_service.create_bot_session(
        db_session,
        strategy_key="ma_crossover",
        tickers=["AAPL"],
        initial_capital=100_000.0,
        benchmark="SP500",
        strategy_params={"fast_period": 2, "slow_period": 3},
    )
    perf_fresh = bot_service.dashboard_performance(
        db_session, fresh, range_=DashboardRange.MAX, today=_TODAY
    )
    assert perf_fresh.current_value == pytest.approx(100_000.0)
    assert perf_fresh.unrealised_pnl == pytest.approx(0.0)


def test_dashboard_performance_pnl_tracks_live_value(db_session: Session) -> None:
    # On the MAX range the baseline is the allocated capital, so the range pnl
    # follows the live (freshest-observation) current value, not the snapshot.
    bot = _make_bot(db_session)
    bot_service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 6, 10)
    )
    _add_value_point(
        db_session,
        bot,
        when=datetime.now(UTC) + timedelta(hours=1),
        value=105_000.0,
        unrealised=5_000.0,
    )

    perf = bot_service.dashboard_performance(
        db_session, bot, range_=DashboardRange.MAX, today=_TODAY
    )

    assert perf.current_value == pytest.approx(105_000.0)
    assert perf.pnl == pytest.approx(perf.current_value - 100_000.0)


def test_dashboard_performance_shape(db_session: Session) -> None:
    bot = _make_bot(db_session)
    bot_service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=date(2026, 6, 10)
    )
    _seed_benchmark(db_session)

    perf = bot_service.dashboard_performance(
        db_session, bot, range_=DashboardRange.MAX, today=_TODAY
    )

    assert perf.kind == "bot"
    assert perf.allocated_capital == 100_000.0
    assert [p.date for p in perf.points] == [date(2026, 6, 10)]
    assert len(perf.contributions) == 1
    assert perf.contributions[0].amount == 100_000.0
    assert perf.contributions[0].effective_date == date(2026, 6, 10)
    # 100k invested in the index at 100 valued at 110 -> 110k.
    assert perf.benchmark_value == pytest.approx(110_000.0)


def test_dashboard_performance_without_snapshot_anchors_live_point(
    db_session: Session,
) -> None:
    bot = _make_bot(db_session)

    perf = bot_service.dashboard_performance(
        db_session, bot, range_=DashboardRange.MAX, today=_TODAY
    )

    assert perf.kind == "bot"
    assert [p.date for p in perf.points] == [_TODAY]
    assert perf.points[0].value == 100_000.0
    assert perf.contributions[0].effective_date == _TODAY


def test_dashboard_performance_multi_position_value(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "MSFT")
    bot = bot_service.create_bot_session(
        db_session,
        strategy_key="ma_crossover",
        tickers=["AAPL", "MSFT"],
        initial_capital=100_000.0,
        benchmark="SP500",
        strategy_params={"fast_period": 2, "slow_period": 3},
    )
    from cadence.strategy_bots.models import BotPosition

    for ticker, asset_id, qty, avg in (
        ("AAPL", bot.symbols[0].asset_id, 100.0, 50.0),
        ("MSFT", bot.symbols[1].asset_id, 50.0, 20.0),
    ):
        bot.positions.append(
            BotPosition(
                asset_id=asset_id, ticker=ticker, alpaca_symbol=ticker,
                quantity=qty, avg_price=avg, opened_at=_NOW,
            )
        )
        bot.cash -= qty * avg
    db_session.flush()
    bot_service.record_bot_snapshot(
        db_session,
        bot,
        marks={"AAPL": 60.0, "MSFT": 15.0},
        snapshot_date=date(2026, 6, 10),
    )
    _seed_benchmark(db_session)

    perf = bot_service.dashboard_performance(
        db_session, bot, range_=DashboardRange.MAX, today=_TODAY
    )

    # cash = 100k - 5000 - 1000 = 94000; + 100*60 + 50*15 = 94000 + 6750 = 100750.
    assert perf.kind == "bot"
    assert perf.current_value == pytest.approx(100_750.0)
    assert "2 symbols" in perf.label


def test_overview_unions_ai_and_bot_rows(db_session: Session) -> None:
    # One AI session...
    portfolio = portfolios_service.create_portfolio(
        db_session, name="Alpha", stocks=["TECH"]
    )
    paper_trading_service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="s1",
        rebalance_prompt_version=1,
        crypto_rebalance_prompt_version=1,
        allocated_capital=10_000.0,
        benchmark=Benchmark.SP500,
    )
    # ...and one bot session whose earliest snapshot predates the AI session.
    earliest = date(2026, 6, 1)
    bot = _make_bot(db_session)
    bot_service.record_bot_snapshot(
        db_session, bot, marks={}, snapshot_date=earliest
    )
    # Seed a benchmark close exactly on the earliest bot date. Only an overlay
    # floor that reaches back to that date keeps it as a plotted point; a floor
    # anchored at the AI session's later contribution would drop it (keeping only
    # the latest pre-floor close as a rebasing anchor).
    for on, close in ((earliest, 95.0), (date(2026, 6, 10), 100.0), (_TODAY, 110.0)):
        db_session.add(
            BenchmarkPrice(benchmark=Benchmark.SP500.value, price_date=on, close=close)
        )
    db_session.flush()

    overview = dashboard_service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MAX,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    kinds = {perf.kind for perf in overview.sessions}
    assert kinds == {"ai", "bot"}
    # The earliest bot snapshot date is folded into the overlay floor, so the
    # SP500 overlay carries a plotted point on that exact date.
    sp500 = next(
        s for s in overview.benchmark_series if s.benchmark_id == Benchmark.SP500.value
    )
    assert any(point.date == earliest for point in sp500.points)


def test_ai_rows_default_to_ai_kind(db_session: Session) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="Beta", stocks=["TECH"]
    )
    paper_trading_service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="s1",
        rebalance_prompt_version=1,
        crypto_rebalance_prompt_version=1,
        allocated_capital=10_000.0,
        benchmark=Benchmark.SP500,
    )

    overview = dashboard_service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MAX,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    assert [perf.kind for perf in overview.sessions] == ["ai"]
    assert SessionStatus.ACTIVE  # sanity: imported symbol used


def test_orchestrator_bots_are_not_bot_rows(db_session: Session) -> None:
    from cadence.bot_orchestrator import service as orchestrator_service
    from cadence.strategy_bots.constants import BotOrigin

    manual = _make_bot(db_session)
    _add_asset(db_session, "MSFT")
    orchestrator = orchestrator_service.create_orchestrator(
        db_session, label="First Orchestrator", capital=10_000.0
    )
    orchestrator.free_capital -= 3_000.0
    bot_service.create_bot_session(
        db_session,
        preset_key="donchian_turtle_algo25",
        tickers=["MSFT"],
        initial_capital=3_000.0,
        benchmark="SP500",
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )

    rows = bot_service.dashboard_performances(
        db_session, range_=DashboardRange.MAX, today=_TODAY
    )

    assert [r.id for r in rows] == [manual.id]  # type: ignore[attr-defined]
    assert rows[0].kind == "bot"
