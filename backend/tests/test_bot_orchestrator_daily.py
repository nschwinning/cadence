"""Tests for orchestrator daily snapshots and the daily P&L push."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session
from tests.fakes import RecordingNotifier

from cadence.assets.models import Asset
from cadence.bot_orchestrator import daily
from cadence.bot_orchestrator import service as orchestrator_service
from cadence.bot_orchestrator.daily import DailyFigures, StartedBot, StoppedBot
from cadence.bot_orchestrator.models import (
    BotOrchestrator,
    BotOrchestratorRun,
    BotOrchestratorSnapshot,
)
from cadence.paper_trading.models import BenchmarkPrice
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import BotOrigin, StopReason
from cadence.strategy_bots.models import BotSession, BotValueSnapshot

# Tuesday 2026-11-10, 16:15 America/New_York (the evening snapshot job).
_NOW = datetime(2026, 11, 10, 21, 15, tzinfo=UTC)
_TODAY = date(2026, 11, 10)
_MINUS = "−"  # the formatters use a true minus sign


# Builder (pure) ----------------------------------------------------------------
def _figures(**overrides: object) -> DailyFigures:
    base: dict[str, object] = {
        "value": 10_250.0,
        "day_change": 120.0,
        "day_change_pct": 0.0118,
        "total_return": 250.0,
        "total_return_pct": 0.025,
        "free_capital": 4_000.0,
        "allocated_capital": 6_000.0,
        "active_bots": 2,
        "max_bots": 3,
    }
    base.update(overrides)
    return DailyFigures(**base)  # type: ignore[arg-type]


def test_message_core_lines() -> None:
    message = daily.orchestrator_daily_message(_figures())
    lines = message.splitlines()

    assert lines[0] == "$10,250.00 today (+$120.00, +1.18%)"
    assert lines[1] == "Total return: +$250.00 (+2.50%)"
    assert lines[2] == "Free $4,000.00 · Allocated $6,000.00 · Bots 2/3"
    assert "Started: none" in lines
    assert "Stopped: none" in lines
    assert lines[-1] == "No decision run today"


def test_message_omits_percent_without_positive_baseline() -> None:
    message = daily.orchestrator_daily_message(
        _figures(day_change=-50.0, day_change_pct=None)
    )
    assert message.splitlines()[0] == f"$10,250.00 today ({_MINUS}$50.00)"


def test_message_benchmark_line_present_or_omitted() -> None:
    with_benchmark = daily.orchestrator_daily_message(
        _figures(
            benchmark_name="S&P 500", benchmark_return=0.009, excess_return=0.016
        )
    )
    assert "vs S&P 500: +0.90% (excess +1.60%)" in with_benchmark
    assert "vs " not in daily.orchestrator_daily_message(_figures())


def test_message_best_worst_only_and_none() -> None:
    two = daily.orchestrator_daily_message(
        _figures(bot_pnls=[("A on MSFT", 85.0), ("B on AAPL", -12.0)])
    )
    assert f"Best: A on MSFT +$85.00 · Worst: B on AAPL {_MINUS}$12.00" in two
    one = daily.orchestrator_daily_message(_figures(bot_pnls=[("A on MSFT", 5.0)]))
    assert "Only bot: A on MSFT +$5.00" in one
    assert "Best:" not in daily.orchestrator_daily_message(_figures())


def test_message_started_and_stopped_lines() -> None:
    message = daily.orchestrator_daily_message(
        _figures(
            started=[StartedBot("Turtle Breakout (Algo 25) on MSFT, NVDA", 2_500.0)],
            stopped=[
                StoppedBot("RSI Mean Reversion (Algo 16) on AAPL", "orchestrator", 0.018),
                StoppedBot("MA Crossover (Algo 6) on XOM", "drawdown_kill_switch", -0.052),
            ],
        )
    )

    assert "Started: Turtle Breakout (Algo 25) on MSFT, NVDA ($2,500.00)" in message
    assert (
        "Stopped: RSI Mean Reversion (Algo 16) on AAPL — orchestrator (+1.80%); "
        f"MA Crossover (Algo 6) on XOM — kill-switch ({_MINUS}5.20%)"
    ) in message


def test_message_caps_long_lists() -> None:
    started = [StartedBot(f"Bot {i}", 1_000.0) for i in range(7)]
    message = daily.orchestrator_daily_message(_figures(started=started))

    started_line = next(l for l in message.splitlines() if l.startswith("Started:"))
    assert started_line.count("($1,000.00)") == 5
    assert started_line.endswith("+2 more")


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        ("succeeded", None, "Decision run: succeeded"),
        ("partial", None, "Decision run: partial"),
        ("skipped", "not a trading day", "Decision run: skipped"),
        ("failed", "boom", "Decision run: failed — boom"),
    ],
)
def test_message_decision_line(status: str, error: str | None, expected: str) -> None:
    message = daily.orchestrator_daily_message(
        _figures(run_status=status, run_error=error)
    )
    assert message.splitlines()[-1] == expected


def test_message_truncates_long_errors() -> None:
    message = daily.orchestrator_daily_message(
        _figures(run_status="failed", run_error="x" * 200)
    )
    last = message.splitlines()[-1]
    assert last.startswith("Decision run: failed — ")
    assert len(last) == len("Decision run: failed — ") + 80
    assert last.endswith("…")


# Service -----------------------------------------------------------------------
def _asset(db: Session, ticker: str) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db.add(asset)
    db.flush()
    return asset


def _orchestrator(db: Session, label: str = "Core rotation") -> BotOrchestrator:
    return orchestrator_service.create_orchestrator(db, label=label, capital=10_000.0)


def _bot(
    db: Session,
    orchestrator: BotOrchestrator,
    ticker: str,
    capital: float,
    *,
    preset: str = "donchian_turtle_algo25",
    created_at: datetime | None = None,
) -> BotSession:
    orchestrator.free_capital -= capital
    bot = bot_service.create_bot_session(
        db,
        preset_key=preset,
        tickers=[ticker],
        initial_capital=capital,
        benchmark="SP500",
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )
    bot.created_at = created_at or _NOW - timedelta(days=5)
    db.flush()
    return bot


def _bot_snapshots(db: Session, bot: BotSession, yesterday: float, today: float) -> None:
    for day, value in ((_TODAY - timedelta(days=1), yesterday), (_TODAY, today)):
        db.add(
            BotValueSnapshot(
                session=bot,
                snapshot_date=day,
                total_value=value,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            )
        )
    db.flush()


def test_snapshot_records_figures_and_upserts(db_session: Session) -> None:
    _asset(db_session, "MSFT")
    orchestrator = _orchestrator(db_session)
    _bot(db_session, orchestrator, "MSFT", 3_000.0)

    first = daily.record_orchestrator_snapshot(db_session, orchestrator, _TODAY)
    again = daily.record_orchestrator_snapshot(db_session, orchestrator, _TODAY)

    assert first.id == again.id
    assert again.value == pytest.approx(10_000.0)
    assert again.free_capital == pytest.approx(7_000.0)
    assert again.allocated_capital == pytest.approx(3_000.0)
    assert again.active_bots == 1
    count = (
        db_session.query(BotOrchestratorSnapshot)
        .filter(BotOrchestratorSnapshot.orchestrator_id == orchestrator.id)
        .count()
    )
    assert count == 1


def test_previous_and_first_snapshot_lookups(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    for offset in (3, 1, 0):
        daily.record_orchestrator_snapshot(
            db_session, orchestrator, _TODAY - timedelta(days=offset)
        )

    previous = daily.previous_orchestrator_snapshot(
        db_session, orchestrator, before=_TODAY
    )
    first = daily.first_orchestrator_snapshot(db_session, orchestrator)

    assert previous is not None and previous.snapshot_date == _TODAY - timedelta(days=1)
    assert first is not None and first.snapshot_date == _TODAY - timedelta(days=3)


def test_daily_push_end_to_end(db_session: Session) -> None:
    for ticker in ("MSFT", "AAPL", "XOM", "NVDA"):
        _asset(db_session, ticker)
    orchestrator = _orchestrator(db_session)
    # Yesterday's snapshot is the day-change baseline; the first snapshot (3 days ago)
    # starts the benchmark window.
    db_session.add_all(
        [
            BotOrchestratorSnapshot(
                orchestrator_id=orchestrator.id,
                snapshot_date=_TODAY - timedelta(days=3),
                value=10_000.0,
                free_capital=10_000.0,
                allocated_capital=0.0,
                active_bots=0,
            ),
            BotOrchestratorSnapshot(
                orchestrator_id=orchestrator.id,
                snapshot_date=_TODAY - timedelta(days=1),
                value=9_900.0,
                free_capital=4_000.0,
                allocated_capital=6_000.0,
                active_bots=2,
            ),
        ]
    )
    for i, close in enumerate((5_000.0, 5_010.0, 5_020.0, 5_050.0)):
        db_session.add(
            BenchmarkPrice(
                benchmark="SP500",
                price_date=_TODAY - timedelta(days=3 - i),
                close=close,
            )
        )
    winner = _bot(db_session, orchestrator, "MSFT", 3_000.0)
    _bot_snapshots(db_session, winner, 3_000.0, 3_085.0)
    loser = _bot(
        db_session, orchestrator, "AAPL", 3_000.0, preset="rsi_mean_reversion_algo16"
    )
    _bot_snapshots(db_session, loser, 3_000.0, 2_988.0)
    # Deployed this morning (no snapshot of its own yet, so no best/worst entry).
    _bot(db_session, orchestrator, "NVDA", 1_000.0, created_at=_NOW - timedelta(hours=7))
    # Stopped today by its own kill-switch, still selling.
    killed = _bot(db_session, orchestrator, "XOM", 1_000.0, preset="ma_crossover_algo6")
    killed.cash = 950.0
    killed.status = "stopped"
    killed.stop_reason = StopReason.DRAWDOWN_KILL_SWITCH.value
    killed.stopped_at = _NOW - timedelta(hours=2)
    # A run from this morning.
    db_session.add(
        BotOrchestratorRun(
            orchestrator_id=orchestrator.id,
            trigger="scheduled",
            status="partial",
            model="gpt-5-mini",
            created_at=_NOW - timedelta(hours=7, minutes=15),
        )
    )
    db_session.flush()
    notifier = RecordingNotifier()

    count = daily.run_orchestrator_daily(db_session, notifier=notifier, now=_NOW)

    assert count == 1
    assert len(notifier.sent) == 1
    message, title = notifier.sent[0]
    assert title == "Cadence orchestrator: Core rotation daily P&L"
    lines = message.splitlines()
    # free 2,000 + MSFT 3,085 + AAPL 2,988 (today's snapshots) + NVDA 1,000 (no
    # snapshot → cost) + XOM 950 cash = 10,023; yesterday was 9,900.
    assert lines[0] == "$10,023.00 today (+$123.00, +1.24%)"
    assert lines[1] == "Total return: +$23.00 (+0.23%)"
    assert "Bots 3/3" in lines[2]
    # Benchmark +1.00% since the first snapshot; orchestrator +0.23% → excess −0.77%.
    assert f"vs S&P 500: +1.00% (excess {_MINUS}0.77%)" in lines
    assert (
        f"Best: Turtle Breakout (Algo 25) · MSFT +$85.00 · "
        f"Worst: RSI Mean Reversion (Algo 16) · AAPL {_MINUS}$12.00"
    ) in lines
    assert "Started: Turtle Breakout (Algo 25) · NVDA ($1,000.00)" in lines
    assert (
        f"Stopped: MA Crossover (Algo 6) · XOM — kill-switch ({_MINUS}5.00%)" in lines
    )
    assert lines[-1] == "Decision run: partial"
    snapshot = (
        db_session.query(BotOrchestratorSnapshot)
        .filter(
            BotOrchestratorSnapshot.orchestrator_id == orchestrator.id,
            BotOrchestratorSnapshot.snapshot_date == _TODAY,
        )
        .one()
    )
    assert snapshot.value == pytest.approx(10_023.0)


def test_bots_from_other_days_are_not_listed(db_session: Session) -> None:
    _asset(db_session, "MSFT")
    _asset(db_session, "AAPL")
    orchestrator = _orchestrator(db_session)
    _bot(db_session, orchestrator, "MSFT", 2_000.0)  # created 5 days ago
    old_stop = _bot(db_session, orchestrator, "AAPL", 2_000.0)
    old_stop.status = "stopped"
    old_stop.stop_reason = StopReason.ORCHESTRATOR.value
    old_stop.stopped_at = _NOW - timedelta(days=2)
    db_session.flush()
    notifier = RecordingNotifier()

    daily.run_orchestrator_daily(db_session, notifier=notifier, now=_NOW)

    message = notifier.sent[0][0]
    assert "Started: none" in message
    assert "Stopped: none" in message
    assert message.splitlines()[-1] == "No decision run today"
    # Day one: the change is measured against the capital pool.
    assert message.splitlines()[0].startswith("$10,000.00 today (+$0.00, +0.00%)")


def test_stopped_orchestrators_get_no_snapshot_or_push(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    orchestrator_service.stop_orchestrator(db_session, orchestrator.id)
    notifier = RecordingNotifier()

    count = daily.run_orchestrator_daily(db_session, notifier=notifier, now=_NOW)

    assert count == 0
    assert notifier.sent == []
    assert db_session.query(BotOrchestratorSnapshot).count() == 0


def test_notifier_failure_or_absence_still_records(db_session: Session) -> None:
    _orchestrator(db_session, label="A")
    _orchestrator(db_session, label="B")

    assert (
        daily.run_orchestrator_daily(
            db_session, notifier=RecordingNotifier(raises=True), now=_NOW
        )
        == 2
    )
    assert daily.run_orchestrator_daily(db_session, notifier=None, now=_NOW) == 2
    assert db_session.query(BotOrchestratorSnapshot).count() == 2
