"""Recommender service: orchestration for a recommendation run.

A run is created in ``queued``, then executed: the agent proposes candidates,
Cadence re-validates each one server-side, and eligible new assets are added
(up to the requested count). Every phase transition and per-candidate outcome is
persisted so a poller can watch progress and inspect the result.

``add_asset`` from the assets domain commits internally, so an ineligible
candidate is removed with a follow-up delete rather than a savepoint rollback;
the observable result is identical — the ineligible asset is never persisted.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.assets.category import SUPPORTED_CATEGORIES
from cadence.assets.errors import (
    DuplicateAssetError,
    MarketDataUnavailableError,
    UnknownTickerError,
    UnsupportedCategoryError,
    UntradeableTickerError,
)
from cadence.assets.market_data import MarketDataProvider
from cadence.assets.service import add_asset, delete_asset, list_assets
from cadence.broker.base import Broker
from cadence.dashboard.service import get_universe_composition
from cadence.recommendations.agent import (
    RecommenderAgent,
    default_eligibility_criteria,
)
from cadence.recommendations.constants import (
    CANDIDATE_OVERFETCH_FACTOR,
    MIN_CANDIDATES_REQUESTED,
    CandidateOutcome,
    RunPhase,
)
from cadence.recommendations.errors import (
    RecommendationValidationError,
    RunNotFoundError,
)
from cadence.recommendations.models import RecommendationRun


def create_run(
    session: Session,
    count: int,
    categories: list[str],
) -> int:
    """Validate the request and insert a queued run; return its id.

    Raises:
        RecommendationValidationError: if ``count`` is not positive, no category
            is provided, or a category outside the supported set (stock, crypto)
            is requested.
    """
    if count <= 0:
        raise RecommendationValidationError("count must be greater than zero")
    if not categories:
        raise RecommendationValidationError("at least one category is required")
    supported = {c.value for c in SUPPORTED_CATEGORIES}
    unsupported = sorted(set(categories) - supported)
    if unsupported:
        raise RecommendationValidationError(
            f"unsupported categories {unsupported}; only "
            f"{sorted(supported)} are supported"
        )

    run = RecommendationRun(
        status=RunPhase.QUEUED.value,
        requested_count=count,
        requested_categories=list(categories),
        tool_call_count=0,
        results=[],
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run.id


def get_run(session: Session, run_id: int) -> RecommendationRun:
    """Return a run by id or raise :class:`RunNotFoundError`."""
    run = session.get(RecommendationRun, run_id)
    if run is None:
        raise RunNotFoundError(f"Recommendation run {run_id} not found")
    return run


def list_runs(session: Session, limit: int = 20) -> list[RecommendationRun]:
    """Return recent runs, newest first."""
    return list(
        session.execute(
            select(RecommendationRun)
            .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
            .limit(limit)
        ).scalars()
    )


def _candidate_count(requested_count: int) -> int:
    """How many candidates to ask the agent for, given the requested count.

    Overfetch so dedup/eligibility filtering still has enough to reach the
    target; the requested count remains the hard cap on assets actually added.
    """
    return max(MIN_CANDIDATES_REQUESTED, requested_count * CANDIDATE_OVERFETCH_FACTOR)


def execute_run(
    session: Session,
    run_id: int,
    agent: RecommenderAgent,
    provider: MarketDataProvider,
    broker: Broker,
) -> None:
    """Drive a queued run to a terminal phase.

    Advances ``searching`` → ``validating`` → ``completed``. On any failure the
    run is marked ``failed`` with a readable reason; assets added before the
    failure are left intact and no partially-formed asset remains. A broker
    ``ConnectionError`` is systemic (Alpaca unconfigured/unreachable) and fails
    the whole run rather than being swallowed per-candidate.
    """
    run = get_run(session, run_id)
    try:
        criteria = default_eligibility_criteria()
        categories = list(run.requested_categories)
        ask_for = _candidate_count(run.requested_count)
        # Snapshot the universe composition now so the agent is steered toward
        # under-represented sectors; the recorded prompt reflects it.
        composition = get_universe_composition(session)
        # The tickers already in the universe, passed to the agent as a hard
        # exclusion so it stops re-proposing existing assets (server-side dedup
        # remains as a safety net).
        exclude_tickers = [asset.ticker for asset in list_assets(session)]

        # Phase: searching — record the exact prompt, then run the agent.
        run.prompt = agent.build_prompt(
            categories, ask_for, criteria, composition, exclude_tickers
        )
        run.status = RunPhase.SEARCHING.value
        session.commit()

        result = agent.recommend(
            categories, ask_for, criteria, composition, exclude_tickers
        )

        run.tool_call_count = result.tool_call_count
        run.status = RunPhase.VALIDATING.value
        session.commit()

        # Phase: validating — re-validate and add eligible new assets.
        outcomes = _validate_and_add(
            session,
            provider,
            broker,
            candidates=[c.ticker for c in result.output.candidates],
            limit=run.requested_count,
        )
        run.results = outcomes
        run.status = RunPhase.COMPLETED.value
        session.commit()
    except Exception as exc:  # noqa: BLE001 - persisted as the run's failure reason
        session.rollback()
        _mark_failed(session, run_id, str(exc) or exc.__class__.__name__)


def _validate_and_add(
    session: Session,
    provider: MarketDataProvider,
    broker: Broker,
    candidates: list[str],
    limit: int,
) -> list[dict[str, str | None]]:
    """Add eligible, new candidates up to ``limit``; return per-candidate outcomes.

    Reuses ``assets.service.add_asset`` (which enforces its own eligibility
    evaluation and duplicate check). An asset that comes back ineligible is
    deleted again so the hard eligibility filter holds. Adding stops once
    ``limit`` eligible assets have been added.
    """
    outcomes: list[dict[str, str | None]] = []
    added = 0

    for ticker in candidates:
        if added >= limit:
            break
        try:
            asset = add_asset(session, ticker, provider, broker)
        except DuplicateAssetError:
            outcomes.append(_outcome(ticker, CandidateOutcome.SKIPPED_DUPLICATE))
            continue
        except (
            UnknownTickerError,
            MarketDataUnavailableError,
            UnsupportedCategoryError,
            UntradeableTickerError,
        ) as exc:
            # A single bad candidate (unknown, untradeable, or wrong category)
            # is recorded and skipped — it must not fail the whole run.
            outcomes.append(
                _outcome(ticker, CandidateOutcome.ERROR, str(exc) or type(exc).__name__)
            )
            continue

        if not asset.is_eligible:
            # Hard filter: never keep an ineligible asset in the universe.
            delete_asset(session, asset.id)
            outcomes.append(_outcome(ticker, CandidateOutcome.SKIPPED_INELIGIBLE))
            continue

        added += 1
        outcomes.append(_outcome(ticker, CandidateOutcome.ADDED))

    return outcomes


def _outcome(
    ticker: str,
    outcome: CandidateOutcome,
    detail: str | None = None,
) -> dict[str, str | None]:
    return {"ticker": ticker, "outcome": outcome.value, "detail": detail}


def _mark_failed(session: Session, run_id: int, error: str) -> None:
    """Best-effort transition of a run to ``failed`` with a reason."""
    run = session.get(RecommendationRun, run_id)
    if run is None:
        return
    run.status = RunPhase.FAILED.value
    run.error = error
    session.commit()
