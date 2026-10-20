"""Build flow: drive a queued build event to a terminal status.

A build no longer allocates capital. It creates the AI-managed portfolio and the
paper-trading session *shell* (freezing every opt-in, the frozen prompt versions,
the benchmark, and the session metadata), then triggers an **initial rebalance**
inline — through the standard rebalance path — so the opening allocation benefits
from every rebalance-only enhancement (trend gate, fundamentals, the guardrail
clamp, the reserved cash buffer, unexecutable-weight redeploy, sells-before-buys,
and sizing against the session's live value). The build event records the
shell-creation step and references the triggered initial rebalance; the opening
trades are recorded on that rebalance's run.
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy.orm import Session

from cadence.ai_portfolio._helpers import (
    _elapsed_ms,
    _fail_event,
    _finish_event,
    _humanize_failure,
    _risk_profile,
)
from cadence.ai_portfolio.agent import AIPortfolioAgent
from cadence.ai_portfolio.constants import (
    AI_STRATEGY_KEY,
    EventStatus,
    PromptKind,
)
from cadence.ai_portfolio.events import create_rebalance_event, get_event
from cadence.ai_portfolio.flows.rebalance import run_rebalance_event
from cadence.ai_portfolio.params import AIBuildParams
from cadence.ai_portfolio.prompts import get_active_rebalance_prompt
from cadence.assets.market_data import MarketDataProvider
from cadence.broker.base import Broker
from cadence.config import settings
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import Benchmark, ScheduleMode
from cadence.portfolios import service as portfolios_service
from cadence.portfolios.constants import PortfolioSource
from cadence.utils.name_generator import generate_unique_name

logger = logging.getLogger(__name__)


def run_build_event(
    session: Session,
    event_id: uuid.UUID,
    agent: AIPortfolioAgent,
    broker: Broker,
    provider: MarketDataProvider,
) -> None:
    """Drive a queued build event to a terminal status.

    The build creates the portfolio + session shell and places no opening orders;
    the opening allocation is produced by an initial rebalance that this flow
    triggers inline. The initial rebalance runs regardless of the session's
    schedule mode, so a manual session is allocated at creation and does not sit
    empty; a daily session is additionally enrolled in the scheduled job.
    """
    t0 = time.monotonic()
    event = get_event(session, event_id)
    event.status = EventStatus.RUNNING.value
    session.commit()

    try:
        params = AIBuildParams.from_payload(event.request_payload or {})
        # Freeze the currently active rebalance-prompt versions onto the session so
        # every rebalance for it (including the opening one) uses these versions,
        # regardless of later prompt edits.
        active_prompt = get_active_rebalance_prompt(session)
        active_crypto_prompt = get_active_rebalance_prompt(
            session, kind=PromptKind.CRYPTO_REBALANCE
        )

        # The AI names every build generically (e.g. "AI Growth"), so portfolios
        # collide and their sessions become indistinguishable. Generate a distinct,
        # human-friendly name instead.
        portfolio_name = generate_unique_name(
            risk_profile=params.risk_profile,
            existing_names=portfolios_service.list_portfolio_names(session),
        )
        # The per-asset guardrail cap repurposes ``max_allocation_pct`` (a no-op
        # 1.0 when guardrails are off) so both the portfolio and session freeze it.
        per_asset_cap = (
            params.max_allocation_pct
            if params.risk_guardrails_enabled
            and params.max_allocation_pct is not None
            else 1.0
        )
        # Shell portfolio: no holdings yet. The inline initial rebalance populates
        # its end-state (``update_portfolio_stocks``) once it allocates.
        portfolio = portfolios_service.create_portfolio(
            session,
            name=portfolio_name,
            stocks=[],
            source=PortfolioSource.AI_MANAGED,
            risk_profile=_risk_profile(params.risk_profile),
            max_allocation_pct=per_asset_cap,
            source_run_id=str(event.id),
            allow_empty=True,
        )

        schedule_mode = (
            ScheduleMode.DAILY_REBALANCING
            if params.daily_rebalancing
            else ScheduleMode.MANUAL
        )
        session_row = paper_service.create_session(
            session,
            portfolio_id=portfolio.id,
            strategy_key=AI_STRATEGY_KEY,
            rebalance_prompt_version=active_prompt.version,
            crypto_rebalance_prompt_version=active_crypto_prompt.version,
            allocated_capital=params.allocated_capital,
            max_allocation_pct=portfolio.max_allocation_pct,
            schedule_mode=schedule_mode,
            benchmark=Benchmark(params.benchmark),
            use_technical_indicators=params.use_technical_indicators,
            stop_loss_enabled=params.stop_loss_enabled,
            stop_loss_pct=params.stop_loss_pct,
            risk_guardrails_enabled=params.risk_guardrails_enabled,
            max_asset_class_pct=params.max_asset_class_pct,
            min_positions=params.min_positions,
            max_invested_pct=params.max_invested_pct,
            learning_feedback_enabled=params.learning_feedback_enabled,
            # Freeze the window when opting in: use the chosen value, else the
            # configured default. Disabled sessions carry no window.
            learning_feedback_window=(
                (
                    params.learning_feedback_window
                    or settings.LEARNING_FEEDBACK_DEFAULT_WINDOW
                )
                if params.learning_feedback_enabled
                else None
            ),
            use_fundamentals=params.use_fundamentals,
        )
        session_row.session_metadata = {
            "session_type": "ai_managed",
            "risk_profile": params.risk_profile,
            "asset_types": params.asset_types,
            "build_event_id": str(event.id),
            "portfolio_id": str(portfolio.id),
        }
        event.session_id = session_row.id
        event.portfolio_id = portfolio.id
        session.commit()

        # The opening allocation is a rebalance: create a rebalance event for the
        # new session, record its id on the session so the build-order readiness
        # gate follows it (D3), then drive it DIRECTLY — not via the single-worker
        # job runner, which would deadlock the build job (D2). No notifier: the
        # build path is silent, like a manual rebalance.
        rebalance_event = create_rebalance_event(session, session_row.id)
        session_row.session_metadata = {
            **(session_row.session_metadata or {}),
            "initial_rebalance_event_id": str(rebalance_event.id),
        }
        session.commit()

        run_rebalance_event(session, rebalance_event.id, agent, broker, provider)

        # The build event is the shell-creation + opening-allocation-trigger step;
        # it places no trades of its own and finishes succeeded once the shell
        # exists and the initial rebalance has been triggered (the rebalance event
        # carries its own terminal status and the opening trades).
        _finish_event(
            session,
            event,
            EventStatus.SUCCEEDED,
            result_payload={"initial_rebalance_event_id": str(rebalance_event.id)},
            actions_taken=[],
            duration_ms=_elapsed_ms(t0),
        )
        logger.info(
            "AI portfolio build %s created shell; initial rebalance %s triggered",
            event.id,
            rebalance_event.id,
        )
    except Exception as exc:  # noqa: BLE001 - persisted as the event's failure reason
        session.rollback()
        logger.error("AI portfolio build %s failed: %s", event_id, exc)
        _fail_event(
            session,
            event_id,
            _humanize_failure(exc),
            _elapsed_ms(t0),
        )
