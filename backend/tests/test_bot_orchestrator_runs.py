"""Unit tests for orchestrator decision runs: validation, execution, scheduling."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session
from tests.fakes import FakeOrchestratorAgent, RecordingNotifier

from cadence.assets.models import Asset
from cadence.bot_orchestrator import runs
from cadence.bot_orchestrator import service as orchestrator_service
from cadence.bot_orchestrator.agent import (
    DeployAction,
    OrchestratorDecision,
    StopAction,
)
from cadence.bot_orchestrator.constants import OrchestratorTrigger
from cadence.bot_orchestrator.errors import (
    OrchestratorNotActiveError,
    OrchestratorRunInProgressError,
)
from cadence.bot_orchestrator.models import BotOrchestrator, BotOrchestratorRun
from cadence.broker.base import BrokerError
from cadence.broker.stub import StubBroker
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import BotOrigin
from cadence.strategy_bots.market_data import BarsResult
from cadence.strategy_bots.models import BotSession

# Tuesday 2026-11-10, 09:00 America/New_York (pre-open).
_PRE_OPEN = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)


class _CalendarBroker(StubBroker):
    """Stub broker with a configurable trading-day answer (or calendar failure)."""

    def __init__(self, *, trading_day: bool = True, fails: bool = False) -> None:
        super().__init__()
        self._trading_day = trading_day
        self._fails = fails
        self.market_open = True

    def is_trading_day(self, day: date) -> bool:
        if self._fails:
            raise BrokerError("calendar down")
        return self._trading_day

    def is_market_open(self) -> bool:
        return self.market_open


def _no_sentiment(tickers: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
    return {t: {"status": "unavailable"} for t in tickers}


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


def _orchestrator(db: Session, **overrides: object) -> BotOrchestrator:
    kwargs: dict[str, object] = {"label": "Core", "capital": 10_000.0}
    kwargs.update(overrides)
    return orchestrator_service.create_orchestrator(db, **kwargs)  # type: ignore[arg-type]


def _deployed_bot(
    db: Session, orchestrator: BotOrchestrator, capital: float, ticker: str
) -> BotSession:
    orchestrator.free_capital -= capital
    return bot_service.create_bot_session(
        db,
        preset_key="ma_crossover_algo6",
        tickers=[ticker],
        initial_capital=capital,
        benchmark="SP500",
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )


def _execute(
    db: Session,
    orchestrator: BotOrchestrator,
    agent: FakeOrchestratorAgent,
    *,
    broker: StubBroker | None = None,
    notifier: RecordingNotifier | None = None,
    trigger: OrchestratorTrigger = OrchestratorTrigger.MANUAL,
) -> BotOrchestratorRun:
    run = runs.queue_run(db, orchestrator, trigger)
    return runs.execute_run(
        db,
        run.id,
        agent=agent,
        broker=broker or _CalendarBroker(),
        notifier=notifier,
        now=_PRE_OPEN,
        resolve_sentiment=_no_sentiment,
    )


def _deploy(preset: str, tickers: list[str], capital: float) -> DeployAction:
    return DeployAction(
        preset_key=preset, tickers=tickers, capital=capital, rationale="fits"
    )


# Validation ------------------------------------------------------------------
def _state(**overrides: object) -> runs.DecisionState:
    base: dict[str, Any] = {
        "active_bot_ids": {"bot-1"},
        "eligible_tickers": {"AAPL", "MSFT", "XOM"},
        "preset_keys": {"ma_crossover_algo6", "donchian_turtle_algo25"},
        "free_capital": 5_000.0,
        "open_slots": 1,
        "max_bot_capital": 4_000.0,
        "max_tickers_per_bot": 2,
    }
    base.update(overrides)
    return runs.DecisionState(**base)


@pytest.mark.parametrize(
    ("deploy", "reason"),
    [
        (_deploy("nope", ["AAPL"], 2_000), "unknown preset"),
        (_deploy("ma_crossover_algo6", [], 2_000), "no tickers"),
        (_deploy("ma_crossover_algo6", ["AAPL", "aapl"], 2_000), "duplicate"),
        (_deploy("ma_crossover_algo6", ["AAPL", "MSFT", "XOM"], 2_000), "per-bot limit"),
        (_deploy("ma_crossover_algo6", ["TSLA"], 2_000), "not eligible"),
        (_deploy("ma_crossover_algo6", ["AAPL"], 999), "below"),
        (_deploy("ma_crossover_algo6", ["AAPL"], 4_500), "per-bot maximum"),
    ],
)
def test_each_invalid_deploy_is_rejected(deploy: DeployAction, reason: str) -> None:
    result = runs.validate_decision(
        OrchestratorDecision(market_summary="x", deploys=[deploy]), _state()
    )

    assert result.deploys == []
    assert len(result.rejected) == 1
    assert reason in result.rejected[0]["reason"]


def test_deploy_above_free_capital_rejected() -> None:
    result = runs.validate_decision(
        OrchestratorDecision(
            market_summary="x",
            deploys=[_deploy("ma_crossover_algo6", ["AAPL"], 3_000)],
        ),
        _state(free_capital=2_500.0),
    )

    assert "free capital" in result.rejected[0]["reason"]


def test_no_slot_left_rejected_and_capital_accumulates() -> None:
    result = runs.validate_decision(
        OrchestratorDecision(
            market_summary="x",
            deploys=[
                _deploy("ma_crossover_algo6", ["AAPL"], 2_000),
                _deploy("donchian_turtle_algo25", ["msft"], 2_000),
            ],
        ),
        _state(),
    )

    assert [d.tickers for d in result.deploys] == [["AAPL"]]
    assert "no bot slot" in result.rejected[0]["reason"]


def test_stop_of_a_foreign_or_unknown_bot_rejected() -> None:
    result = runs.validate_decision(
        OrchestratorDecision(
            market_summary="x",
            stops=[
                StopAction(bot_id="someone-else", reason="r"),
                StopAction(bot_id="bot-1", reason="r"),
                StopAction(bot_id="bot-1", reason="again"),
            ],
        ),
        _state(),
    )

    assert [s.bot_id for s in result.stops] == ["bot-1"]
    assert len(result.rejected) == 2


def test_a_stop_frees_its_slot_for_a_later_deploy() -> None:
    result = runs.validate_decision(
        OrchestratorDecision(
            market_summary="x",
            stops=[StopAction(bot_id="bot-1", reason="setup gone")],
            deploys=[
                _deploy("ma_crossover_algo6", ["AAPL"], 2_000),
                _deploy("donchian_turtle_algo25", ["MSFT"], 2_000),
            ],
        ),
        _state(open_slots=0),
    )

    assert len(result.stops) == 1
    assert [d.preset_key for d in result.deploys] == ["ma_crossover_algo6"]
    assert "no bot slot" in result.rejected[0]["reason"]


# Execution -------------------------------------------------------------------
def test_run_stops_and_deploys(db_session: Session) -> None:
    _asset(db_session, "AAPL")
    _asset(db_session, "MSFT")
    orchestrator = _orchestrator(db_session)
    old = _deployed_bot(db_session, orchestrator, 3_000.0, "AAPL")
    agent = FakeOrchestratorAgent(
        decision=OrchestratorDecision(
            market_summary="Rotation into breakouts.",
            stops=[StopAction(bot_id=str(old.id), reason="trend broke")],
            deploys=[_deploy("donchian_turtle_algo25", ["msft"], 2_500)],
        )
    )

    run = _execute(db_session, orchestrator, agent)

    assert run.status == "succeeded"
    assert run.error is None
    assert run.prompt_version == 1
    assert run.briefing is not None and run.decision is not None
    assert old.status == "stopped" and old.stop_reason == "orchestrator"
    deploys = [a for a in run.applied or [] if a["kind"] == "deploy"]
    assert len(deploys) == 1
    new_bot = db_session.get(BotSession, uuid.UUID(deploys[0]["bot_id"]))
    assert new_bot is not None
    assert new_bot.origin == "orchestrator"
    assert new_bot.orchestrator_id == orchestrator.id
    assert new_bot.preset_key == "donchian_turtle_algo25"
    assert [s.ticker for s in new_bot.symbols] == ["MSFT"]
    assert new_bot.initial_capital == 2_500.0
    # 10,000 - 3,000 (old) - 2,500 (new) + 3,000 (old bot was flat, cash returned).
    assert orchestrator.free_capital == pytest.approx(7_500.0)
    assert agent.calls[0][1] == orchestrator.model


def test_run_with_an_over_budget_deploy_is_partial(db_session: Session) -> None:
    _asset(db_session, "AAPL")
    _asset(db_session, "MSFT")
    orchestrator = _orchestrator(db_session)
    agent = FakeOrchestratorAgent(
        decision=OrchestratorDecision(
            market_summary="x",
            deploys=[
                _deploy("ma_crossover_algo6", ["AAPL"], 4_000),
                _deploy("donchian_turtle_algo25", ["MSFT"], 9_000),
            ],
        )
    )

    run = _execute(db_session, orchestrator, agent)

    assert run.status == "partial"
    assert len(run.applied or []) == 1
    assert len(run.rejected or []) == 1
    assert orchestrator.free_capital == pytest.approx(6_000.0)


def test_run_fails_without_changes_on_agent_timeout(db_session: Session) -> None:
    _asset(db_session, "AAPL")
    orchestrator = _orchestrator(db_session)
    bot = _deployed_bot(db_session, orchestrator, 3_000.0, "AAPL")

    run = _execute(db_session, orchestrator, FakeOrchestratorAgent(fail=True))

    assert run.status == "failed"
    assert run.error is not None and "timed out" in run.error
    assert run.briefing is not None  # the briefing is still recorded
    assert bot.status == "active"
    assert orchestrator.free_capital == pytest.approx(7_000.0)
    # A failed run does not count toward the cadence.
    assert runs.orchestrator_due(db_session, orchestrator, _PRE_OPEN)


def test_run_fails_when_every_action_is_rejected(db_session: Session) -> None:
    _asset(db_session, "AAPL")
    orchestrator = _orchestrator(db_session)
    agent = FakeOrchestratorAgent(
        decision=OrchestratorDecision(
            market_summary="x", deploys=[_deploy("nope", ["AAPL"], 2_000)]
        )
    )

    run = _execute(db_session, orchestrator, agent)

    assert run.status == "failed"
    assert run.error == "every action in the decision was rejected"
    assert orchestrator.free_capital == 10_000.0


def test_no_action_decision_succeeds(db_session: Session) -> None:
    # Weekly, so the counting run makes it not due for the rest of the week.
    orchestrator = _orchestrator(db_session, cadence="weekly")

    run = _execute(db_session, orchestrator, FakeOrchestratorAgent())

    assert run.status == "succeeded"
    assert run.applied == [] and run.rejected == []
    assert not runs.orchestrator_due(db_session, orchestrator, _PRE_OPEN)


def test_run_is_skipped_on_a_non_trading_day(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    agent = FakeOrchestratorAgent()

    run = _execute(
        db_session, orchestrator, agent, broker=_CalendarBroker(trading_day=False)
    )

    assert run.status == "skipped"
    assert agent.calls == []
    assert runs.orchestrator_due(db_session, orchestrator, _PRE_OPEN)


def test_run_fails_when_the_calendar_is_unavailable(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    agent = FakeOrchestratorAgent()

    run = _execute(db_session, orchestrator, agent, broker=_CalendarBroker(fails=True))

    assert run.status == "failed"
    assert run.error is not None and "calendar" in run.error
    assert agent.calls == []


def test_pre_open_deploy_waits_for_the_open(db_session: Session) -> None:
    """A deploy made before the open trades nothing until the market is open."""
    _asset(db_session, "AAPL")
    orchestrator = _orchestrator(db_session)
    broker = _CalendarBroker()
    broker.market_open = False
    agent = FakeOrchestratorAgent(
        decision=OrchestratorDecision(
            market_summary="x", deploys=[_deploy("ma_crossover_algo6", ["AAPL"], 3_000)]
        )
    )

    run = _execute(db_session, orchestrator, agent, broker=broker)

    class _Bars:
        def latest_bars(
            self, symbol: str, timeframe: str, count: int, *, now: datetime
        ) -> BarsResult:  # pragma: no cover - never reached while closed
            raise AssertionError("no bars are fetched while the market is closed")

    tick = bot_service.run_tick(
        db_session, broker=broker, market_data=_Bars(), now=_PRE_OPEN
    )
    assert run.status == "succeeded"
    assert tick.market_open is False
    bot_id = (run.applied or [])[0]["bot_id"]
    bot = db_session.get(BotSession, uuid.UUID(bot_id))
    assert bot is not None and bot.total_trades == 0


def test_stopped_orchestrator_run_is_skipped(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    run = runs.queue_run(db_session, orchestrator, OrchestratorTrigger.MANUAL)
    orchestrator_service.stop_orchestrator(db_session, orchestrator.id)

    result = runs.execute_run(
        db_session,
        run.id,
        agent=FakeOrchestratorAgent(),
        broker=_CalendarBroker(),
        now=_PRE_OPEN,
        resolve_sentiment=_no_sentiment,
    )

    assert result.status == "skipped"


# Notifications ---------------------------------------------------------------
def test_scheduled_run_notifies_a_summary(db_session: Session) -> None:
    _asset(db_session, "AAPL")
    orchestrator = _orchestrator(db_session)
    notifier = RecordingNotifier()
    agent = FakeOrchestratorAgent(
        decision=OrchestratorDecision(
            market_summary="x", deploys=[_deploy("donchian_turtle_algo25", ["AAPL"], 2_000)]
        )
    )

    _execute(
        db_session,
        orchestrator,
        agent,
        notifier=notifier,
        trigger=OrchestratorTrigger.SCHEDULED,
    )

    assert len(notifier.sent) == 1
    message, title = notifier.sent[0]
    assert title == "Orchestrator Core"
    assert "Deployed: Turtle Breakout (Algo 25) on AAPL" in message


def test_scheduled_failure_notifies(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    notifier = RecordingNotifier()

    _execute(
        db_session,
        orchestrator,
        FakeOrchestratorAgent(fail=True),
        notifier=notifier,
        trigger=OrchestratorTrigger.SCHEDULED,
    )

    assert notifier.sent and "Decision run failed" in notifier.sent[0][0]


def test_manual_run_is_silent(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    notifier = RecordingNotifier()

    _execute(db_session, orchestrator, FakeOrchestratorAgent(), notifier=notifier)

    assert notifier.sent == []


def test_notifier_failure_does_not_fail_the_run(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)

    run = _execute(
        db_session,
        orchestrator,
        FakeOrchestratorAgent(),
        notifier=RecordingNotifier(raises=True),
        trigger=OrchestratorTrigger.SCHEDULED,
    )

    assert run.status == "succeeded"


# Scheduling ------------------------------------------------------------------
def _finished_run(
    db: Session, orchestrator: BotOrchestrator, status: str, finished_at: datetime
) -> None:
    db.add(
        BotOrchestratorRun(
            orchestrator_id=orchestrator.id,
            trigger="scheduled",
            status=status,
            model=orchestrator.model,
            finished_at=finished_at,
        )
    )
    db.flush()


def test_daily_orchestrator_is_always_due(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    _finished_run(db_session, orchestrator, "succeeded", _PRE_OPEN)

    assert runs.orchestrator_due(db_session, orchestrator, _PRE_OPEN)


def test_weekly_not_due_within_the_same_iso_week(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session, cadence="weekly")
    monday = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
    _finished_run(db_session, orchestrator, "partial", monday)

    assert not runs.orchestrator_due(db_session, orchestrator, _PRE_OPEN)
    next_week = datetime(2026, 11, 16, 14, 0, tzinfo=UTC)
    assert runs.orchestrator_due(db_session, orchestrator, next_week)


def test_weekly_due_again_after_a_failed_run(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session, cadence="weekly")
    _finished_run(db_session, orchestrator, "failed", datetime(2026, 11, 9, 14, tzinfo=UTC))

    assert runs.orchestrator_due(db_session, orchestrator, _PRE_OPEN)


def test_monthly_boundary(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session, cadence="monthly")
    _finished_run(db_session, orchestrator, "succeeded", datetime(2026, 11, 3, 14, tzinfo=UTC))

    assert not runs.orchestrator_due(db_session, orchestrator, _PRE_OPEN)
    assert runs.orchestrator_due(
        db_session, orchestrator, datetime(2026, 12, 1, 14, tzinfo=UTC)
    )


def test_queue_run_rejects_a_second_live_run(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    runs.queue_run(db_session, orchestrator, OrchestratorTrigger.MANUAL)

    with pytest.raises(OrchestratorRunInProgressError):
        runs.queue_run(db_session, orchestrator, OrchestratorTrigger.MANUAL)


def test_queue_run_rejects_an_inactive_orchestrator(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    orchestrator_service.stop_orchestrator(db_session, orchestrator.id)

    with pytest.raises(OrchestratorNotActiveError):
        runs.queue_run(db_session, orchestrator, OrchestratorTrigger.MANUAL)


def test_queue_due_runs_counts(db_session: Session) -> None:
    due = _orchestrator(db_session, label="Due")
    weekly = _orchestrator(db_session, label="Weekly", cadence="weekly")
    _finished_run(db_session, weekly, "succeeded", datetime(2026, 11, 9, 14, tzinfo=UTC))
    busy = _orchestrator(db_session, label="Busy")
    runs.queue_run(db_session, busy, OrchestratorTrigger.MANUAL)

    result = runs.queue_due_runs(db_session, now=_PRE_OPEN)

    assert [r.orchestrator_id for r in result.queued] == [due.id]
    assert result.queued[0].trigger == "scheduled"
    assert result.not_due == 1
    assert result.already_running == 1


def test_orphaned_live_runs_are_failed(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    run = runs.queue_run(db_session, orchestrator, OrchestratorTrigger.MANUAL)

    assert runs.fail_orphaned_runs(db_session) == 1
    assert run.status == "failed"
    assert run.error == "interrupted by a restart"


# Usage & trace ---------------------------------------------------------------
def test_completed_run_stores_usage(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)

    run = _execute(db_session, orchestrator, FakeOrchestratorAgent())

    assert run.usage == {
        "requests": 2,
        "input_tokens": 1_000,
        "output_tokens": 234,
        "total_tokens": 1_234,
    }


def test_timed_out_and_skipped_runs_store_no_usage(db_session: Session) -> None:
    failed_orchestrator = _orchestrator(db_session, label="Fails")
    failed = _execute(db_session, failed_orchestrator, FakeOrchestratorAgent(fail=True))
    holiday_orchestrator = _orchestrator(db_session, label="Holiday")
    skipped = _execute(
        db_session,
        holiday_orchestrator,
        FakeOrchestratorAgent(),
        broker=_CalendarBroker(trading_day=False),
    )

    assert failed.status == "failed" and failed.usage is None
    assert skipped.status == "skipped" and skipped.usage is None


def test_run_is_traced_with_its_run_trace_id(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager

    traced: list[str | None] = []

    @contextmanager
    def _capture(trace_id: str | None, **kwargs: object) -> Any:
        traced.append(trace_id)
        yield

    monkeypatch.setattr(runs, "llm_trace", _capture)
    orchestrator = _orchestrator(db_session)

    run = _execute(db_session, orchestrator, FakeOrchestratorAgent())

    assert traced == [runs.run_trace_id(run.id)]
    assert runs.run_trace_id(run.id) == f"orchestrator-run-{run.id}"
