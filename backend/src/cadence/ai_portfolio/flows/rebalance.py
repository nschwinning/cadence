"""Rebalance flow: drive a queued rebalance event to a terminal status.

Guards on market hours / crypto tradability (recording a skip when there is nothing
to trade), runs the agent for desired end-state target weights, trades the deltas
via the executor (sizing against the session's live value or the crypto budget),
records trades/closed positions/a run, updates the portfolio end-state, and marks
the event terminal. Supports the weekend ``crypto_only`` mode.
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
    _apply_rebalance_trades,
    _asset_class_map,
    _build_holdings,
    _build_run_stats,
    _candidates_from_universe,
    _elapsed_ms,
    _exclude_unexecutable_candidates,
    _fail_event,
    _finish_event,
    _fractionable_map,
    _gate_discovered,
    _guardrail_caps,
    _guardrail_instruction,
    _humanize_failure,
    _involves_crypto,
    _min_positions_observation,
    _normalize_tickers,
    _snapshots_by_ticker,
)
from cadence.ai_portfolio.agent import AIPortfolioAgent
from cadence.ai_portfolio.constants import (
    TREND_PROMPT_VERSION,
    EventStatus,
    PromptKind,
)
from cadence.ai_portfolio.events import get_event
from cadence.ai_portfolio.executor import AIPortfolioExecutor
from cadence.ai_portfolio.notifications import (
    _notify_rebalance_skipped,
    _notify_safely,
    _rebalance_success_message,
)
from cadence.ai_portfolio.prompts import get_rebalance_prompt_by_version
from cadence.assets import service as assets_service
from cadence.assets.category import AssetCategory, AssetScope, scope_categories
from cadence.assets.market_data import MarketDataProvider
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, Position
from cadence.config import settings
from cadence.notify.base import Notifier
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import RunStatus
from cadence.portfolios import service as portfolios_service
from cadence.technical_indicators import service as ti_service

logger = logging.getLogger(__name__)


def run_rebalance_event(
    session: Session,
    event_id: uuid.UUID,
    agent: AIPortfolioAgent,
    broker: Broker,
    provider: MarketDataProvider,
    notifier: Notifier | None = None,
    crypto_only: bool = False,
) -> None:
    """Drive a queued rebalance event to a terminal status.

    When the market is closed the job is a no-op: a ``skipped`` run is recorded
    (no orders) and the event is marked ``skipped``. Otherwise the agent returns
    desired end-state target weights across the full universe (with bounded
    discovery), and the executor trades the deltas toward those weights.

    ``crypto_only`` runs the weekend crypto-only mode: the session's asset scope is
    intersected with crypto, BOTH the candidate set and the considered holdings are
    restricted to crypto (so equities are never assigned a target and never sold —
    see design D3), the crypto sleeve is sized against a crypto budget (crypto
    positions' market value + the session's unallocated cash) rather than the
    allocated capital, and the session's frozen ``crypto_rebalance`` prompt is used.
    A crypto-only run for a session with no crypto held or targeted is skipped
    before the agent is consulted.

    ``notifier`` is optional: the daily cron path supplies one so an executed
    rebalance (or a failure) is pushed to the user; manual rebalances leave it
    ``None`` and stay silent. Sending is best-effort — a notifier that fails or
    raises never affects the rebalance outcome (see :func:`_notify_safely`).
    """
    t0 = time.monotonic()
    event = get_event(session, event_id)
    event.status = EventStatus.RUNNING.value
    session.commit()

    # Bound at ``with`` entry (below) so research captured before a mid-run failure
    # is still persisted on the (failed) event; stays empty on the skip path.
    research: list[dict[str, Any]] = []
    # Assembled at the candidate/holdings seam so a mid-run failure keeps it; stays
    # null on the skip path and for sessions frozen to a pre-trend prompt version.
    trend_context: dict[str, Any] | None = None
    try:
        if event.session_id is None:
            raise ValueError("rebalance event has no session")
        session_id = event.session_id
        session_row = paper_service.get_session(session, session_id)
        portfolio = portfolios_service.get_portfolio(session, session_row.portfolio_id)

        # Read the scope and risk profile persisted at build. Sessions built before
        # these fields existed default to ``both`` / ``balanced`` (unchanged
        # behaviour). ``risk_profile`` was previously written but never re-read here,
        # so every rebalance silently ran as the agent's default.
        metadata = session_row.session_metadata or {}
        asset_scope = str(metadata.get("asset_types", AssetScope.BOTH.value))
        risk_profile = str(metadata.get("risk_profile", "balanced"))
        allowed_categories = scope_categories(asset_scope)
        if crypto_only:
            # Weekend crypto-only mode: regardless of the session's own scope, only
            # the crypto sleeve is tended (D2). Intersecting here restricts the
            # candidate universe to crypto below.
            allowed_categories = allowed_categories & frozenset(
                {AssetCategory.CRYPTO}
            )

        # Crypto trades 24/7, so the market-open guard can no longer skip the
        # whole run unconditionally. Read this session's holdings from its ledger
        # (the source of truth) and the class map first, to decide whether anything
        # is tradable while the equities market is closed.
        market_open = broker.is_market_open()
        universe = assets_service.list_assets(session)
        asset_classes = _asset_class_map(universe)

        full_ledger = paper_service.list_open_positions(session, session_id)
        # In crypto-only mode the considered holdings are restricted to crypto so
        # equities are never assigned a target and never sold (D3). Everywhere the
        # run reads holdings (positions passed to the executor, held-ticker set,
        # trend snapshots, agent holdings) uses this scoped view.
        if crypto_only:
            ledger = [
                entry
                for entry in full_ledger
                if asset_classes.get(entry.ticker, AssetClass.EQUITY)
                == AssetClass.CRYPTO
            ]
        else:
            ledger = full_ledger
        positions = {
            entry.ticker: Position(
                symbol=entry.ticker,
                quantity=entry.quantity,
                avg_cost=entry.avg_cost,
            )
            for entry in ledger
        }

        # Targets considered for the "is anything tradable" check are the portfolio's
        # current end-state holdings, restricted to crypto in crypto-only mode.
        candidate_targets = (
            [t for t in portfolio.stocks
             if asset_classes.get(_normalize_tickers([t])[0], AssetClass.EQUITY)
             == AssetClass.CRYPTO]
            if crypto_only
            else portfolio.stocks
        )
        any_crypto = _involves_crypto(positions, candidate_targets, asset_classes)

        # Value the session once (marked to market) and reason off its OWN free
        # cash, not the shared broker's global buying power (D5). ``cash_value`` is
        # the session's unallocated cash; the crypto budget (crypto positions'
        # market value + that cash) sizes the crypto-only sleeve. Computed here —
        # ahead of the pre-agent skip — so a crypto-only run can test whether it has
        # any deployable cash to buy crypto before paying for an agent call.
        valuation = paper_service.compute_session_value(
            session, session_id=session_id, broker=broker
        )
        crypto_budget = (
            sum(
                p["market_value"]
                for p in valuation.positions
                if asset_classes.get(p["ticker"], AssetClass.EQUITY)
                == AssetClass.CRYPTO
            )
            + valuation.cash_value
        )

        # Nothing tradable — skip before ever consulting the agent:
        #  - crypto-only: no crypto held or targeted, OR the session holds no crypto
        #    and has no deployable cash to buy crypto (free cash, net of the reserved
        #    buffer, is <= 0) — it can neither rotate existing crypto nor deploy cash.
        #    This catches a crypto-scoped session holding only equity shares with no
        #    free capital. The buffer reserve mirrors the executor's: a crypto run
        #    reserves the greater of the percentage buffer and the crypto fee
        #    estimate (``CRYPTO_FEE_PCT`` of the budget, a conservative bound).
        #  - full run: the equities market is closed and no crypto is held/targeted.
        # ``crypto_skip_reason`` captures *which* crypto condition fired so the
        # user-facing notification states the true reason rather than asserting
        # both — a stocks-only session skips purely for "holds no crypto" and may
        # well have ample free cash, so claiming "no free cash" would be wrong.
        crypto_skip_reason: str | None = None
        if crypto_only:
            has_crypto_positions = any(
                asset_classes.get(ticker, AssetClass.EQUITY) == AssetClass.CRYPTO
                for ticker in positions
            )
            crypto_reserve = max(
                crypto_budget * settings.REBALANCE_CASH_BUFFER_PCT,
                crypto_budget * settings.CRYPTO_FEE_PCT,
            )
            crypto_deployable_cash = valuation.cash_value - crypto_reserve
            if not any_crypto:
                crypto_skip_reason = "holds no crypto to rebalance"
            elif not has_crypto_positions and crypto_deployable_cash <= 0.0:
                crypto_skip_reason = "no free cash to buy crypto"
            nothing_tradable = crypto_skip_reason is not None
        else:
            nothing_tradable = not market_open and not any_crypto

        if nothing_tradable:
            skip_reason = "no crypto" if crypto_only else "market closed"
            paper_service.record_session_run(
                session,
                session_id=session_id,
                signals_scanned=0,
                signals_actionable=0,
                orders_executed=0,
                orders_skipped=0,
                details=[{"skipped": True, "reason": skip_reason}],
                status=RunStatus.SUCCESS,
                run_trigger="ai_rebalance",
                duration_ms=_elapsed_ms(t0),
                ai_portfolio_event_id=event.id,
            )
            _finish_event(
                session,
                event,
                EventStatus.SKIPPED,
                result_payload=None,
                actions_taken=[],
                duration_ms=_elapsed_ms(t0),
            )
            logger.info("AI rebalance %s skipped: %s", event.id, skip_reason)
            # Inform the user that the engaged run did nothing and why. A no-op when
            # no notifier is supplied (manual rebalance) — see _notify_rebalance_skipped.
            notify_reason = (
                crypto_skip_reason or "holds no crypto to rebalance"
                if crypto_only
                else "market closed with nothing to trade"
            )
            _notify_rebalance_skipped(
                notifier, portfolio.name, notify_reason, crypto_only=crypto_only
            )
            return

        # The trend gate and its per-run context apply only when this session opted
        # into the technical-indicator trend strategy at build time AND is frozen to
        # the trend prompt version (or later). Sessions that opted out (the default,
        # including every session built before the opt-in existed) or on an earlier
        # (pre-trend) prompt version keep their original ungated behaviour and record
        # no trend context.
        gating_enabled = (
            session_row.use_technical_indicators
            and session_row.rebalance_prompt_version >= TREND_PROMPT_VERSION
        )

        # A freshly stopped-out position is quarantined for a cooldown window so the
        # agent cannot immediately re-buy it. Exclude quarantined tickers the session
        # does not currently hold (regardless of the trend opt-in); once the
        # quarantine expires the ticker becomes a candidate again. Held tickers are
        # never excluded so the agent can still decide to keep or sell them.
        held_tickers = {entry.ticker for entry in ledger if entry.quantity}
        quarantined_tickers = paper_service.list_active_quarantined_tickers(
            session, session_id
        )

        def _is_quarantined(ticker: str) -> bool:
            return ticker in quarantined_tickers and ticker not in held_tickers

        # Candidates are restricted to the session's asset scope; the full universe
        # (above) still backs the class map so held positions stay classified.
        scoped_universe = [
            asset
            for asset in universe
            if asset.category in allowed_categories and not _is_quarantined(asset.ticker)
        ]
        # Drop tickers the brokerage cannot trade (e.g. a legacy dot-suffixed
        # foreign listing like ``ASML.AS``) so the agent stops re-targeting a name
        # that can never fill. This filters only the candidates offered to the
        # agent; held positions remain in the rebalance's trade set and can still be
        # exited.
        scoped_universe, excluded_candidates = _exclude_unexecutable_candidates(
            scoped_universe, asset_classes, broker
        )
        candidate_snapshots = (
            ti_service.get_latest_snapshots(
                session, [asset.id for asset in scoped_universe]
            )
            if gating_enabled
            else {}
        )
        candidates, dropped_candidates = _candidates_from_universe(
            scoped_universe, candidate_snapshots, apply_gate=gating_enabled
        )
        dropped_candidates.extend(excluded_candidates)
        holding_snapshots = (
            _snapshots_by_ticker(
                session, [entry.ticker for entry in ledger if entry.quantity]
            )
            if gating_enabled
            else None
        )
        holdings = _build_holdings(
            ledger, broker, asset_classes, holding_snapshots
        )
        if gating_enabled:
            trend_context = {
                "dropped_candidates": dropped_candidates,
                "candidates": [
                    {"ticker": c["ticker"], "indicators": c["indicators"]}
                    for c in candidates
                ],
                "holdings": [
                    {
                        "ticker": h["ticker"],
                        "indicators": h["indicators"],
                        "reversal_flags": h["reversal_flags"],
                    }
                    for h in holdings
                ],
            }
        # ``valuation`` and ``crypto_budget`` were computed above (ahead of the
        # pre-agent skip) off this session's own free cash (D5).
        account_summary = {
            "portfolio_value": valuation.total_value,
            "cash_available": valuation.cash_value,
            "total_unrealized_pnl": valuation.unrealized_pnl,
        }
        if crypto_only:
            account_summary["crypto_budget"] = crypto_budget

        # Use the prompt version frozen onto the session at build time, not
        # whatever is active now, so newer prompt versions never change an
        # already-built session's behavior. A crypto-only run uses the session's
        # frozen crypto-scoped prompt (its own kind + version).
        if crypto_only:
            prompt = get_rebalance_prompt_by_version(
                session,
                session_row.crypto_rebalance_prompt_version,
                kind=PromptKind.CRYPTO_REBALANCE,
            )
        else:
            prompt = get_rebalance_prompt_by_version(
                session, session_row.rebalance_prompt_version
            )
        rebalance_guardrails = _guardrail_instruction(
            enabled=bool(session_row.risk_guardrails_enabled),
            max_asset_pct=session_row.max_allocation_pct,
            max_asset_class_pct=session_row.max_asset_class_pct,
            min_positions=session_row.min_positions,
            max_invested_pct=session_row.max_invested_pct,
        )
        # Learning feedback (opt-in, frozen at build): when enabled, fetch the
        # session's most recent daily-run snapshots (bounded by its frozen window)
        # and pass them as advisory prior-outcome context. Disabled ⇒ no DB read and
        # a byte-identical prompt.
        recent_outcomes: list[dict[str, Any]] | None = None
        if session_row.learning_feedback_enabled:
            window = (
                session_row.learning_feedback_window
                or settings.LEARNING_FEEDBACK_DEFAULT_WINDOW
            )
            snapshots = paper_service.list_daily_run_snapshots(
                session, session_id=session_id, limit=window
            )
            recent_outcomes = [
                {"run_date": s.run_date.isoformat(), "document": s.document}
                for s in snapshots
            ]
        with record_web_searches() as research:
            result = agent.rebalance(
                holdings=holdings,
                account_summary=account_summary,
                candidates=candidates,
                risk_profile=risk_profile,
                instructions=prompt.instructions,
                input_template=prompt.input_template,
                guardrails=rebalance_guardrails,
                recent_outcomes=recent_outcomes,
            )
        agent_output = result.model_dump(mode="json")

        # Best-effort add of any discovered target ticker not yet in the universe;
        # out-of-scope discoveries are rejected inside ``_add_discovered_assets``.
        universe_tickers = {a.ticker for a in universe}
        target_tickers = _normalize_tickers(
            [t.ticker for t in result.target_allocations]
        )
        discovered = [
            t
            for t in target_tickers
            if t not in universe_tickers and not _is_quarantined(t)
        ]
        if gating_enabled:
            # A discovered ticker that already has a stored snapshot failing the
            # gate is dropped; genuinely new tickers (no snapshot) are still added.
            discovered, discovered_dropped = _gate_discovered(session, discovered)
            if trend_context is not None:
                trend_context["dropped_candidates"].extend(discovered_dropped)
        _add_discovered_assets(
            session, discovered, provider, broker, scope=asset_scope
        )

        # Rebuild the class and fractionability maps so any discovered crypto
        # target is classified and each equity's fractionability is known.
        universe = assets_service.list_assets(session)
        asset_classes = _asset_class_map(universe)
        fractionable = _fractionable_map(universe)

        # Read the guardrail config back off the frozen session row; a disabled or
        # pre-migration session yields no caps and the executor stays normalize-only.
        caps = _guardrail_caps(
            enabled=bool(session_row.risk_guardrails_enabled),
            max_asset_pct=session_row.max_allocation_pct,
            max_asset_class_pct=session_row.max_asset_class_pct,
            max_invested_pct=session_row.max_invested_pct,
        )
        # Size the rebalance against the session's current marked-to-market value
        # (current positions' market value + free cash), not the frozen allocated
        # capital, so realised/unrealised gains are redeployed and losses size the
        # targets down. This is the same valuation the KPIs and snapshots use. A
        # crypto-only run sizes against the crypto budget (crypto market value +
        # unallocated cash) so the crypto weights never claim equity capital (D4).
        rebalance_base = crypto_budget if crypto_only else valuation.total_value
        executor = AIPortfolioExecutor(broker, session_row.allocated_capital)
        trade_results = executor.execute_rebalance(
            targets=result.target_allocations,
            current_positions=positions,
            asset_classes=asset_classes,
            market_open=market_open,
            caps=caps,
            base_capital=rebalance_base,
            crypto_only=crypto_only,
            unallocated_cash=valuation.cash_value,
            fractionable=fractionable,
        )

        # The executor planned a buy-only run with no deployable cash and submitted
        # nothing (most visibly the first rebalance right after a build). Record a
        # SKIPPED run — no trades applied — and inform the user it was a no-op.
        if executor.skipped_noop:
            paper_service.record_session_run(
                session,
                session_id=session_id,
                signals_scanned=len(candidates),
                signals_actionable=0,
                orders_executed=0,
                orders_skipped=0,
                details=[{"skipped": True, "reason": "buy-only, no deployable cash"}],
                status=RunStatus.SUCCESS,
                run_trigger="ai_rebalance",
                duration_ms=_elapsed_ms(t0),
                ai_portfolio_event_id=event.id,
            )
            _finish_event(
                session,
                event,
                EventStatus.SKIPPED,
                result_payload=agent_output,
                actions_taken=[],
                duration_ms=_elapsed_ms(t0),
                research=research,
                trend_context=trend_context,
            )
            logger.info(
                "AI rebalance %s skipped: buy-only with no deployable cash", event.id
            )
            _notify_rebalance_skipped(
                notifier,
                portfolio.name,
                "already deployed — buy-only with no free cash",
                crypto_only=crypto_only,
            )
            return

        executed, realized_pnl = _apply_rebalance_trades(
            session,
            session_id,
            trade_results,
            event_id=event.id,
            asset_classes=asset_classes,
        )

        paper_service.record_session_run(
            session,
            session_id=session_id,
            signals_scanned=len(candidates),
            signals_actionable=executed,
            orders_executed=executed,
            orders_skipped=0,
            details=[tr.to_dict() for tr in trade_results],
            status=RunStatus.SUCCESS,
            run_trigger="ai_rebalance",
            duration_ms=_elapsed_ms(t0),
            ai_portfolio_event_id=event.id,
        )
        paper_service.update_session_last_run(
            session, session_id, trades_delta=executed, pnl_delta=realized_pnl
        )

        # End-state holdings are the targets with a non-trivial weight.
        end_state = sorted(
            {
                _normalize_tickers([t.ticker])[0]
                for t in result.target_allocations
                if t.allocation_pct > 0 and t.ticker.strip()
            }
        )
        if end_state and set(end_state) != set(portfolio.stocks):
            portfolios_service.update_portfolio_stocks(session, portfolio.id, end_state)

        all_executed = all(tr.executed for tr in trade_results)
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
                realized_pnl=realized_pnl,
                account_summary=account_summary,
                trend_context=trend_context,
                guardrail_observations=_min_positions_observation(
                    rebalance_guardrails,
                    sum(
                        1
                        for t in result.target_allocations
                        if t.allocation_pct > 0
                    ),
                ),
            ),
        )
        logger.info("AI rebalance %s completed: %s trades executed", event.id, executed)

        # Notify only when the daily path supplied a notifier and orders actually
        # went out; a run that executed nothing is not worth a push. A crypto-only
        # run reuses this same path, labelled so the user can tell the weekend
        # crypto cadence apart from the full weekday rebalance.
        if notifier is not None and executed > 0:
            label = "crypto rebalanced" if crypto_only else "rebalanced"
            _notify_safely(
                notifier,
                title=f"Cadence: {portfolio.name} {label}",
                message=_rebalance_success_message(
                    portfolio.name, trade_results, realized_pnl
                ),
            )
    except Exception as exc:  # noqa: BLE001 - persisted as the event's failure reason
        session.rollback()
        logger.error("AI rebalance %s failed: %s", event_id, exc)
        reason = _humanize_failure(exc)
        _fail_event(
            session,
            event_id,
            reason,
            _elapsed_ms(t0),
            research=research,
            trend_context=trend_context,
        )
        if notifier is not None:
            _notify_safely(
                notifier,
                title="Cadence: daily rebalance failed",
                message=f"Rebalance {event_id} failed: {reason}",
            )
