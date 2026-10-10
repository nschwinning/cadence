"""Build flow: drive a queued build event to a terminal status.

Runs the agent over the (optionally trend-gated) asset universe, creates the
AI-managed portfolio and paper-trading session, sizes and places opening orders via
the executor, records the trades and a session run, and marks the event terminal.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from cadence.agents.tools import record_web_searches
from cadence.ai_portfolio._helpers import (
    _add_discovered_assets,
    _asset_class_map,
    _build_run_stats,
    _candidates_from_universe,
    _elapsed_ms,
    _fail_event,
    _finish_event,
    _fractionable_map,
    _gate_discovered,
    _guardrail_caps,
    _guardrail_instruction,
    _humanize_failure,
    _min_positions_observation,
    _normalize_tickers,
    _record_trades,
    _risk_profile,
)
from cadence.ai_portfolio.agent import AIPortfolioAgent
from cadence.ai_portfolio.constants import (
    AI_STRATEGY_KEY,
    TREND_PROMPT_VERSION,
    EventStatus,
    PromptKind,
)
from cadence.ai_portfolio.events import get_event
from cadence.ai_portfolio.executor import AIPortfolioExecutor
from cadence.ai_portfolio.params import AIBuildParams
from cadence.ai_portfolio.prompts import get_active_rebalance_prompt
from cadence.assets import service as assets_service
from cadence.assets.category import scope_categories
from cadence.assets.market_data import MarketDataProvider
from cadence.broker.base import Broker
from cadence.config import settings
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import Benchmark, RunStatus, ScheduleMode
from cadence.portfolios import service as portfolios_service
from cadence.portfolios.constants import PortfolioSource
from cadence.technical_indicators import service as ti_service
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

    The agent allocates over the full current asset universe and may discover a
    bounded number of new assets; discovered tickers are added to the universe
    best-effort via ``provider``.
    """
    t0 = time.monotonic()
    event = get_event(session, event_id)
    event.status = EventStatus.RUNNING.value
    session.commit()

    # Bound at ``with`` entry so any research/trend context captured before a
    # mid-run failure is still persisted on the (failed) event.
    research: list[dict[str, Any]] = []
    trend_context: dict[str, Any] | None = None
    try:
        params = AIBuildParams.from_payload(event.request_payload or {})
        allowed_categories = scope_categories(params.asset_types)
        universe = assets_service.list_assets(
            session, categories=[c.value for c in allowed_categories]
        )
        # The trend gate and its per-run context apply only when this build opted
        # into the technical-indicator trend strategy AND the active (highest)
        # prompt version is the trend strategy (i.e. after the v3 migration). When
        # the build opts out — the default — or the active prompt predates the trend
        # strategy, the build stays ungated and records no trend context.
        active_prompt = get_active_rebalance_prompt(session)
        # Freeze the active crypto-rebalance prompt version too, for the weekend
        # crypto-only run (mirrors the weekday rebalance-prompt freeze below).
        active_crypto_prompt = get_active_rebalance_prompt(
            session, kind=PromptKind.CRYPTO_REBALANCE
        )
        gating_enabled = (
            params.use_technical_indicators
            and active_prompt.version >= TREND_PROMPT_VERSION
        )
        snapshots = (
            ti_service.get_latest_snapshots(
                session, [asset.id for asset in universe]
            )
            if gating_enabled
            else {}
        )
        candidates, dropped_candidates = _candidates_from_universe(
            universe, snapshots, apply_gate=gating_enabled
        )
        if gating_enabled:
            trend_context = {
                "dropped_candidates": dropped_candidates,
                "candidates": [
                    {"ticker": c["ticker"], "indicators": c["indicators"]}
                    for c in candidates
                ],
                "holdings": [],
            }

        build_guardrails = _guardrail_instruction(
            enabled=params.risk_guardrails_enabled,
            max_asset_pct=params.max_allocation_pct,
            max_asset_class_pct=params.max_asset_class_pct,
            min_positions=params.min_positions,
            max_invested_pct=params.max_invested_pct,
        )
        with record_web_searches() as research:
            result = agent.build(
                candidates=candidates,
                risk_profile=params.risk_profile,
                guardrails=build_guardrails,
            )
        agent_output = result.model_dump(mode="json")

        stock_tickers = _normalize_tickers([s.ticker for s in result.stocks])
        universe_tickers = {a.ticker for a in universe}
        discovered = [t for t in stock_tickers if t not in universe_tickers]
        if gating_enabled:
            # A discovered ticker that already has a stored snapshot failing the
            # gate is dropped from the candidate set; genuinely new tickers (no
            # snapshot) are still added and traded.
            discovered, discovered_dropped = _gate_discovered(session, discovered)
            if trend_context is not None:
                trend_context["dropped_candidates"].extend(discovered_dropped)
        _add_discovered_assets(
            session, discovered, provider, broker, scope=params.asset_types
        )

        # The AI names every build generically (e.g. "AI Growth"), so portfolios
        # collide and their sessions become indistinguishable. Generate a distinct,
        # human-friendly name instead; the AI's thesis is still kept as the
        # description.
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
        portfolio = portfolios_service.create_portfolio(
            session,
            name=portfolio_name,
            stocks=stock_tickers,
            source=PortfolioSource.AI_MANAGED,
            description=result.overall_thesis[:500],
            risk_profile=_risk_profile(params.risk_profile),
            max_allocation_pct=per_asset_cap,
            source_run_id=str(event.id),
        )

        schedule_mode = (
            ScheduleMode.DAILY_REBALANCING
            if params.daily_rebalancing
            else ScheduleMode.MANUAL
        )
        # Freeze the currently active rebalance-prompt version onto the session so
        # every rebalance for it uses this version, regardless of later prompt edits.
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

        # Re-read the universe so discovered crypto is classified, then build the
        # per-ticker class and fractionability maps threaded into the executor.
        universe = assets_service.list_assets(session)
        asset_classes = _asset_class_map(universe)
        fractionable = _fractionable_map(universe)

        caps = _guardrail_caps(
            enabled=params.risk_guardrails_enabled,
            max_asset_pct=params.max_allocation_pct,
            max_asset_class_pct=params.max_asset_class_pct,
            max_invested_pct=params.max_invested_pct,
        )
        executor = AIPortfolioExecutor(broker, params.allocated_capital)
        trade_results = executor.execute_build(
            result.stocks,
            asset_classes=asset_classes,
            caps=caps,
            fractionable=fractionable,
        )

        executed = _record_trades(
            session,
            session_row.id,
            trade_results,
            signal_prefix="ai_build",
            event_id=event.id,
            asset_classes=asset_classes,
        )
        paper_service.record_session_run(
            session,
            session_id=session_row.id,
            signals_scanned=len(result.stocks),
            signals_actionable=len(result.stocks),
            orders_executed=executed,
            orders_skipped=len(result.stocks) - executed,
            details=[tr.to_dict() for tr in trade_results],
            status=RunStatus.SUCCESS,
            run_trigger="ai_build",
            duration_ms=_elapsed_ms(t0),
            ai_portfolio_event_id=event.id,
        )
        paper_service.update_session_last_run(
            session, session_row.id, trades_delta=executed
        )

        all_executed = bool(trade_results) and all(tr.executed for tr in trade_results)
        status = EventStatus.SUCCEEDED if all_executed else EventStatus.PARTIAL
        _finish_event(
            session,
            event,
            status,
            result_payload=agent_output,
            actions_taken=[tr.to_dict() for tr in trade_results],
            duration_ms=_elapsed_ms(t0),
            research=research,
            trend_context=trend_context,
            run_stats=_build_run_stats(
                trade_results=trade_results,
                executed=executed,
                all_executed=all_executed,
                trend_context=trend_context,
                guardrail_observations=_min_positions_observation(
                    build_guardrails,
                    sum(1 for s in result.stocks if s.allocation_pct > 0),
                ),
            ),
        )
        logger.info(
            "AI portfolio build %s completed: %s/%s trades executed",
            event.id,
            executed,
            len(result.stocks),
        )
    except Exception as exc:  # noqa: BLE001 - persisted as the event's failure reason
        session.rollback()
        logger.error("AI portfolio build %s failed: %s", event_id, exc)
        _fail_event(
            session,
            event_id,
            _humanize_failure(exc),
            _elapsed_ms(t0),
            research=research,
            trend_context=trend_context,
        )
