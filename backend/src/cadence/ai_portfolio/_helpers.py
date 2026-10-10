"""Shared private helpers for the AI-portfolio service.

Pure/low-level building blocks reused across the build, rebalance, close, snapshot
and stop-loss code paths: executor-side-to-order-action mapping, asset-class and
fractionability maps, guardrail construction, candidate/holding assembly, trade
recording, and event finalisation. This module is a leaf — it imports only the
domain services and models, never the flows/notifications/snapshots/stop-loss
modules — so it can be imported from anywhere without a cycle.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from agents.exceptions import MaxTurnsExceeded
from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.ai_portfolio.agent import GuardrailInstruction
from cadence.ai_portfolio.constants import EventStatus
from cadence.ai_portfolio.executor import GuardrailCaps, TradeResult
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.assets import service as assets_service
from cadence.assets.category import AssetCategory, AssetScope, scope_categories
from cadence.assets.market_data import MarketDataProvider
from cadence.assets.models import Asset
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, OrderSide, Position
from cadence.config import settings
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.models import SessionPosition
from cadence.portfolios.constants import RiskProfile
from cadence.technical_indicators import service as ti_service
from cadence.technical_indicators.models import TechnicalIndicator

logger = logging.getLogger(__name__)

_VALID_RISK_PROFILES = {profile.value for profile in RiskProfile}


#: Executor trade side -> broker order action stored on the paper trade. The
#: flows are long-only: "long" is a buy (open/increase), "sell" a reduce/close.
_ORDER_ACTION = {
    "long": OrderSide.BUY,
    "sell": OrderSide.SELL,
}


def _order_action(side: str) -> OrderSide:
    return _ORDER_ACTION.get(side, OrderSide.BUY)


def _asset_class_map(assets: list[Asset]) -> dict[str, AssetClass]:
    """Map each asset's ticker to its :class:`AssetClass` (crypto iff category).

    The asset record is the single source of truth: a ticker is crypto iff its
    ``category == AssetCategory.CRYPTO``. Tickers not present in the universe are
    absent from the map; callers default them to :attr:`AssetClass.EQUITY`.
    """
    return {
        asset.ticker: (
            AssetClass.CRYPTO
            if asset.category == AssetCategory.CRYPTO.value
            else AssetClass.EQUITY
        )
        for asset in assets
    }


def _fractionable_map(assets: list[Asset]) -> dict[str, bool]:
    """Map each asset's ticker to whether the brokerage lists it as fractionable.

    The asset record is the single source of truth: only a ``fractionable is True``
    row is sized fractionally. ``False`` and unknown/``NULL`` (and tickers absent
    from the universe) map to ``False`` so the executor keeps whole-share sizing —
    the fractional path is strictly opt-in per asset.
    """
    return {asset.ticker: asset.fractionable is True for asset in assets}


def _guardrail_caps(
    *,
    enabled: bool,
    max_asset_pct: float | None,
    max_asset_class_pct: float | None,
    max_invested_pct: float | None,
) -> GuardrailCaps | None:
    """Build :class:`GuardrailCaps` from a frozen guardrail config, or ``None``.

    Returns ``None`` when guardrails are disabled (or the frozen config predates
    the feature) so the executor keeps its normalize-only path. A missing cap
    (``None`` while enabled) is treated as no-op (1.0) for that dimension.
    """
    if not enabled:
        return None
    return GuardrailCaps(
        max_per_asset=max_asset_pct if max_asset_pct is not None else 1.0,
        max_per_class=(
            max_asset_class_pct if max_asset_class_pct is not None else 1.0
        ),
        max_invested=max_invested_pct if max_invested_pct is not None else 1.0,
    )


def _guardrail_instruction(
    *,
    enabled: bool,
    max_asset_pct: float | None,
    max_asset_class_pct: float | None,
    min_positions: int | None,
    max_invested_pct: float | None,
) -> GuardrailInstruction | None:
    """Build the advisory :class:`GuardrailInstruction` told to the AI, or ``None``.

    Returns ``None`` when guardrails are disabled so the prompt carries no
    guardrail block. Includes ``min_positions`` (which the deterministic clamp
    cannot enforce) so the AI can plan to meet the diversification floor.
    """
    if not enabled:
        return None
    return GuardrailInstruction(
        max_per_asset=max_asset_pct if max_asset_pct is not None else 1.0,
        max_per_class=(
            max_asset_class_pct if max_asset_class_pct is not None else 1.0
        ),
        min_positions=min_positions if min_positions is not None else 1,
        max_invested=max_invested_pct if max_invested_pct is not None else 1.0,
    )


def _involves_crypto(
    positions: dict[str, Position],
    target_tickers: list[str],
    asset_classes: dict[str, AssetClass],
) -> bool:
    """Whether any held position or current target ticker is crypto.

    Used to decide, while the equities market is closed, whether there is any
    tradable crypto (24/7) or the run is a true no-op. ``target_tickers`` are the
    portfolio's current end-state holdings.
    """
    tickers = set(positions) | set(target_tickers)
    return any(
        asset_classes.get(ticker, AssetClass.EQUITY) == AssetClass.CRYPTO
        for ticker in tickers
    )


def _indicator_annotation(snap: TechnicalIndicator) -> dict[str, Any]:
    """The trend-indicator values handed to the AI for a candidate or holding."""
    return {
        "trading_date": snap.trading_date.isoformat() if snap.trading_date else None,
        "close": snap.close,
        "sma_50": snap.sma_50,
        "sma_200": snap.sma_200,
        "close_sma200": snap.close_sma200,
        "sma50_sma200": snap.sma50_sma200,
        "sma200_slope": snap.sma200_slope,
        "ema_20": snap.ema_20,
        "macd_line": snap.macd_line,
        "macd_signal": snap.macd_signal,
        "macd_hist": snap.macd_hist,
        "rsi_14": snap.rsi_14,
        "roc_120": snap.roc_120,
        "obv": snap.obv,
        "obv_change_20d": snap.obv_change_20d,
        "vol_ratio_50": snap.vol_ratio_50,
        "dist_high_52w": snap.dist_high_52w,
        "drawdown_from_max": snap.drawdown_from_max,
        "hvol_20": snap.hvol_20,
        "bb_pctb": snap.bb_pctb,
        "bb_width": snap.bb_width,
        "gate_pass": snap.gate_pass,
        "regime_pass": snap.regime_pass,
        "momentum_pass": snap.momentum_pass,
        "obv_rising": snap.obv_rising,
    }


def _reversal_annotation(snap: TechnicalIndicator) -> dict[str, Any]:
    """The deterministic reversal flags handed to the AI for a holding."""
    return {
        "macd_hist_rollover": snap.rev_macd_hist_rollover,
        "rsi_rollover": snap.rev_rsi_rollover,
        "return_decel": snap.rev_return_decel,
        "obv_price_divergence": snap.rev_obv_price_divergence,
        "sma200_slope_flattening": snap.rev_sma200_slope_flattening,
    }


def _gate_failure_reason(snap: TechnicalIndicator) -> str:
    """Name the gate condition a dropped candidate failed (for the run context)."""
    if not snap.regime_pass:
        return "regime not confirmed (close>SMA200, SMA50>SMA200, SMA200 slope>=0)"
    if not snap.momentum_pass:
        return "momentum not confirmed (MACD hist>0, RSI14>50, ROC120>0)"
    return "trend gate failed"


def _candidates_from_universe(
    assets: list[Asset],
    snapshots: dict[int, TechnicalIndicator],
    *,
    apply_gate: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the candidate records the agent reasons over from the universe.

    Returns ``(candidates, dropped)``. When ``apply_gate`` is true (trend
    strategy), each in-scope asset is kept only if it has a stored snapshot whose
    uptrend gate passes; survivors are annotated with their trend indicators, and
    assets that fail the gate or lack a snapshot are dropped from the candidate set
    (never shown to the AI) and returned in ``dropped`` with the reason. When
    ``apply_gate`` is false (pre-trend prompt version), every asset is a candidate
    with no indicator annotation and nothing is dropped (original behaviour).
    """
    candidates: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for asset in assets:
        base = {
            "ticker": asset.ticker,
            "company_name": asset.name or asset.ticker,
            "sector": asset.sector or "unknown",
            "category": asset.category,
            "is_eligible": asset.is_eligible,
        }
        if not apply_gate:
            candidates.append(base)
            continue
        snap = snapshots.get(asset.id)
        if snap is None:
            dropped.append({"ticker": asset.ticker, "reason": "no snapshot"})
            continue
        if not snap.gate_pass:
            dropped.append(
                {"ticker": asset.ticker, "reason": _gate_failure_reason(snap)}
            )
            continue
        candidates.append({**base, "indicators": _indicator_annotation(snap)})
    return candidates, dropped


def _exclude_unexecutable_candidates(
    scoped_universe: list[Asset],
    asset_classes: dict[str, AssetClass],
    broker: Broker,
) -> tuple[list[Asset], list[dict[str, Any]]]:
    """Drop universe assets the broker cannot trade from the rebalance candidates.

    An asset with a stored ``alpaca_symbol`` was already verified tradable on the
    brokerage at add-time, so it is kept without re-probing. An asset without one —
    a legacy row added before that verification, e.g. a dot-suffixed foreign
    listing like ``ASML.AS`` — is probed via :meth:`Broker.get_asset`; it is
    excluded only when the broker positively reports it missing or non-tradable. A
    broker error leaves the asset in place (fail open) so a transient outage never
    empties the candidate set. This filters only the candidates offered to the
    agent, not the held-position set a rebalance sells from, so a held but
    now-unexecutable position can still be exited.

    Returns ``(kept, excluded)`` where ``excluded`` carries ``{ticker, reason}``
    records for reporting alongside the gate's dropped candidates.
    """
    kept: list[Asset] = []
    excluded: list[dict[str, Any]] = []
    for asset in scoped_universe:
        if asset.alpaca_symbol:
            kept.append(asset)
            continue
        cls = asset_classes.get(asset.ticker, AssetClass.EQUITY)
        try:
            info = broker.get_asset(asset.ticker, cls)
        except Exception as exc:  # noqa: BLE001 - a broker outage must not prune
            logger.warning(
                "AI rebalance: tradability probe failed for %s: %s",
                asset.ticker,
                exc,
            )
            kept.append(asset)
            continue
        if info is None or not info.tradable:
            excluded.append(
                {"ticker": asset.ticker, "reason": "not tradable on brokerage"}
            )
            continue
        kept.append(asset)
    return kept, excluded


def _snapshots_by_ticker(
    session: Session, tickers: list[str]
) -> dict[str, TechnicalIndicator]:
    """Resolve the latest stored snapshot for each ticker, keyed by ticker."""
    if not tickers:
        return {}
    id_to_ticker = {
        asset.id: asset.ticker
        for asset in session.execute(
            select(Asset).where(Asset.ticker.in_(tickers))
        ).scalars()
    }
    snaps = ti_service.get_latest_snapshots(session, list(id_to_ticker))
    return {id_to_ticker[asset_id]: snap for asset_id, snap in snaps.items()}


def _gate_discovered(
    session: Session, discovered: list[str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Drop discovered tickers whose stored snapshot already fails the trend gate.

    A discovered ticker with no stored snapshot is kept — a genuinely new asset is
    still added and traded, and will be gated as a normal candidate in later runs
    once the nightly job computes its snapshot. One that already has a stored
    snapshot failing the gate is dropped from the candidate set. Returns the
    surviving tickers and the dropped records (ticker + reason).
    """
    if not discovered:
        return [], []
    snaps = _snapshots_by_ticker(session, discovered)
    survivors: list[str] = []
    dropped: list[dict[str, Any]] = []
    for ticker in discovered:
        snap = snaps.get(ticker)
        if snap is not None and not snap.gate_pass:
            dropped.append({"ticker": ticker, "reason": _gate_failure_reason(snap)})
            continue
        survivors.append(ticker)
    return survivors, dropped


def _add_discovered_assets(
    session: Session,
    discovered: list[str],
    provider: MarketDataProvider,
    broker: Broker,
    scope: str = AssetScope.BOTH.value,
) -> list[str]:
    """Best-effort add of newly-proposed tickers to the universe (capped).

    Adds at most :data:`settings.AI_PORTFOLIO_MAX_NEW_ASSETS` tickers. Any add that
    fails (unknown ticker, market data unavailable, duplicate, not tradable on the
    brokerage, or a category outside the session's ``scope``) is logged and
    skipped — a rejected ticker is not added and (being out of scope) not traded.
    """
    allowed_categories = scope_categories(scope)
    added: list[str] = []
    for ticker in discovered[: settings.AI_PORTFOLIO_MAX_NEW_ASSETS]:
        try:
            assets_service.add_asset(
                session,
                ticker,
                provider,
                broker,
                allowed_categories=allowed_categories,
            )
            added.append(ticker)
        except Exception as exc:  # noqa: BLE001 - discovery-add is best-effort
            session.rollback()
            logger.warning("AI discovery: could not add %s: %s", ticker, exc)
    return added


def _normalize_tickers(tickers: list[str]) -> list[str]:
    """Upper-case, strip, drop blanks, and de-duplicate ``tickers`` in order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


def _risk_profile(value: str) -> RiskProfile | None:
    return RiskProfile(value) if value in _VALID_RISK_PROFILES else None


def _build_holdings(
    ledger: list[SessionPosition],
    broker: Broker,
    asset_classes: dict[str, AssetClass],
    snapshots: dict[str, TechnicalIndicator] | None = None,
) -> list[dict[str, Any]]:
    """Build the agent's current-holdings context from the session's ledger.

    Quantity and cost basis come from the ledger (the source of truth); the
    current price is priced live via broker quotes. A ticker whose quote can't be
    fetched is included at a zero current price rather than aborting the run.

    When ``snapshots`` is provided (trend strategy), each holding also carries its
    full indicator set and deterministic reversal flags so the AI can decide
    sell/trim/hold — there is no hard exit. A holding without a stored snapshot
    carries ``None`` for both. When ``snapshots`` is ``None`` (pre-trend prompt
    version) no technical context is attached (original behaviour).
    """
    holdings: list[dict[str, Any]] = []
    for entry in ledger:
        if not entry.quantity:
            continue
        cost = entry.avg_cost or 0.0
        cls = asset_classes.get(entry.ticker, AssetClass.EQUITY)
        try:
            quote = broker.get_quote(entry.ticker, cls)
            current = quote.last or quote.ask or 0.0
        except Exception as exc:  # noqa: BLE001 - pricing is best-effort context
            logger.warning("holdings context: no quote for %s: %s", entry.ticker, exc)
            current = 0.0
        holding: dict[str, Any] = {
            "ticker": entry.ticker,
            "side": "long",
            "quantity": entry.quantity,
            "avg_cost": cost,
            "current_price": current,
            "unrealized_pnl": (current - cost) * entry.quantity,
            "pnl_pct": (current / cost - 1) if cost > 0 else 0.0,
        }
        if snapshots is not None:
            snap = snapshots.get(entry.ticker)
            holding["indicators"] = _indicator_annotation(snap) if snap else None
            holding["reversal_flags"] = _reversal_annotation(snap) if snap else None
        holdings.append(holding)
    return holdings


def _record_trades(
    session: Session,
    session_id: uuid.UUID,
    trade_results: list[TradeResult],
    *,
    signal_prefix: str,
    event_id: uuid.UUID,
    asset_classes: dict[str, AssetClass],
) -> int:
    """Persist each executed trade + open its ledger entry; return the count.

    Build trades are opening buys, so each executed fill opens or increases the
    session's ledger entry at the filled price (the cost basis). ``asset_classes``
    maps each ticker to its class so ``record_trade`` can charge the
    asset-class-aware fee (crypto only); unknown tickers default to equity.
    """
    executed = 0
    for tr in trade_results:
        if not tr.executed:
            continue
        side = _order_action(tr.side)
        paper_service.record_trade(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=side,
            quantity=tr.shares,
            price=tr.price or 0.0,
            signal_type=f"{signal_prefix}_{tr.side}",
            asset_class=asset_classes.get(tr.ticker, AssetClass.EQUITY),
            order_id=tr.order_id,
            order_status=tr.order_status,
            filled_price=tr.filled_price,
            ai_portfolio_event_id=event_id,
        )
        paper_service.apply_fill_to_ledger(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=side,
            shares=tr.shares,
            price=tr.filled_price or tr.price or 0.0,
        )
        executed += 1
    return executed


def _apply_rebalance_trades(
    session: Session,
    session_id: uuid.UUID,
    trade_results: list[TradeResult],
    *,
    event_id: uuid.UUID,
    asset_classes: dict[str, AssetClass],
    signal_prefix: str = "ai_rebalance",
) -> tuple[int, float]:
    """Record rebalance trades + closed positions; return (executed, realized_pnl).

    Every executed fill updates the session's open-position ledger. Sells (side
    ``"sell"``) that reduce or close a long record a closed position for the sold
    quantity, using the ledger entry's weighted-average cost as the entry price and
    its opened date as the entry date — read *before* the sell decrements the
    ledger. The end-state ticker list is derived from the AI targets by the caller,
    so no add/remove bookkeeping is done here. ``signal_prefix`` tags the recorded
    trades (``"ai_rebalance"`` for a rebalance, ``"ai_close"`` for a full
    liquidation). ``asset_classes`` maps each ticker to its class so
    ``record_trade`` can charge the asset-class-aware fee (crypto only); unknown
    tickers default to equity.
    """
    executed = 0
    realized_pnl_total = 0.0
    now = datetime.now(tz=UTC)

    for tr in trade_results:
        if not tr.executed:
            continue
        side = _order_action(tr.side)
        fill_price = tr.filled_price or tr.price or 0.0
        paper_service.record_trade(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=side,
            quantity=tr.shares,
            price=tr.price or 0.0,
            signal_type=f"{signal_prefix}_{tr.side}",
            asset_class=asset_classes.get(tr.ticker, AssetClass.EQUITY),
            order_id=tr.order_id,
            order_status=tr.order_status,
            filled_price=tr.filled_price,
            ai_portfolio_event_id=event_id,
        )
        executed += 1

        # A sell reduces/closes an existing long; record realized P&L from the
        # ledger basis, captured before the fill decrements the entry below.
        if tr.side == "sell":
            basis = paper_service.get_position_entry_basis(
                session, session_id, tr.ticker
            )
            if basis is not None:
                entry_price, entry_date = basis
                exit_price = fill_price or entry_price
                closed = paper_service.record_closed_position(
                    session,
                    session_id=session_id,
                    ticker=tr.ticker,
                    quantity=tr.shares,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    entry_date=entry_date,
                    exit_date=now,
                    ai_portfolio_event_id=event_id,
                )
                realized_pnl_total += closed.realized_pnl

        paper_service.apply_fill_to_ledger(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=side,
            shares=tr.shares,
            price=fill_price,
        )

    return executed, realized_pnl_total


def _finish_event(
    session: Session,
    event: AIPortfolioEvent,
    status: EventStatus,
    *,
    result_payload: dict[str, Any] | None,
    actions_taken: list[dict[str, Any]],
    duration_ms: int,
    research: list[dict[str, Any]] | None = None,
    trend_context: dict[str, Any] | None = None,
    run_stats: dict[str, Any] | None = None,
) -> None:
    event.status = status.value
    event.result_payload = result_payload
    event.actions_taken = actions_taken
    event.duration_ms = duration_ms
    if research:
        event.research = research
    if trend_context:
        event.trend_context = trend_context
    if run_stats:
        event.run_stats = run_stats
    session.commit()


def _fail_event(
    session: Session,
    event_id: uuid.UUID,
    error: str,
    duration_ms: int,
    research: list[dict[str, Any]] | None = None,
    trend_context: dict[str, Any] | None = None,
) -> None:
    """Best-effort transition of an event to ``failed`` with a reason.

    Any research/trend context captured before the failure is persisted so a failed
    run is still reviewable.
    """
    event = session.get(AIPortfolioEvent, event_id)
    if event is None:
        return
    event.status = EventStatus.FAILED.value
    event.error = error
    event.duration_ms = duration_ms
    if research:
        event.research = research
    if trend_context:
        event.trend_context = trend_context
    session.commit()


def _humanize_failure(exc: Exception) -> str:
    """Render an exception as a user-facing failure reason for the event row.

    Most exceptions carry a readable message, but the agents SDK's
    :class:`MaxTurnsExceeded` stringifies to a terse ``"Max turns (N) exceeded"``
    that means nothing to a portfolio owner. Translate it into an actionable
    sentence; everything else falls back to its message (or class name).
    """
    if isinstance(exc, MaxTurnsExceeded):
        return (
            f"The AI reached its step limit ({settings.AI_PORTFOLIO_MAX_TURNS} turns) "
            "before finishing — usually too many web searches or tool calls in one "
            "run. No changes were made. Please retry."
        )
    return str(exc) or exc.__class__.__name__


def _build_run_stats(
    *,
    trade_results: list[TradeResult],
    executed: int,
    all_executed: bool,
    realized_pnl: float | None = None,
    account_summary: dict[str, Any] | None = None,
    trend_context: dict[str, Any] | None = None,
    guardrail_observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the machine-readable run-outcome blob for offline learning.

    Captures order counts, full per-trade details (including ``filled_price``,
    which ``actions_taken`` drops), the run's realized P&L and account/valuation
    snapshot where applicable, trend-gate counts derived from ``trend_context``,
    and any guardrail observations (e.g. the AI returning fewer holdings than the
    configured minimum). Deliberately not exposed via the API/UI (see
    ``AIPortfolioEvent.run_stats``).
    """
    stats: dict[str, Any] = {
        "orders": {
            "executed": executed,
            "skipped": len(trade_results) - executed,
            "total": len(trade_results),
            "all_executed": all_executed,
        },
        "trades": [tr.to_stats_dict() for tr in trade_results],
    }
    if realized_pnl is not None:
        stats["realized_pnl"] = realized_pnl
    if account_summary is not None:
        stats["account"] = account_summary
    if trend_context is not None:
        stats["gate"] = {
            "candidates": len(trend_context.get("candidates", [])),
            "dropped": len(trend_context.get("dropped_candidates", [])),
            "holdings": len(trend_context.get("holdings", [])),
        }
    if guardrail_observations:
        stats["guardrails"] = guardrail_observations
    return stats


def _min_positions_observation(
    guardrails: GuardrailInstruction | None, num_positions: int
) -> dict[str, Any] | None:
    """Return a min-positions guardrail observation when the AI under-diversified.

    Min positions is not enforced by fabricating holdings (see design D3); when
    the AI returns fewer positions than the configured minimum the shortfall is
    recorded here for offline learning and the run still succeeds. Returns
    ``None`` when guardrails are off or the minimum is met.
    """
    if guardrails is None:
        return None
    if num_positions >= guardrails.min_positions:
        return None
    return {
        "min_positions": {
            "required": guardrails.min_positions,
            "returned": num_positions,
            "shortfall": guardrails.min_positions - num_positions,
        }
    }


def _elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
