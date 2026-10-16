"""Assets resource router. Mounted under ``/api/v1``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from cadence.api.cron_auth import require_valid_cron_token
from cadence.api.schemas import (
    AssetCreate,
    AssetDetailHistoryPoint,
    AssetDetailRead,
    AssetFundamentalsRead,
    AssetListResponse,
    AssetRead,
    AssetUniverseEvaluationRead,
    AssetUniverseEvaluationResponse,
    FundamentalsRefreshRead,
)
from cadence.assets import service
from cadence.assets.category import AssetCategory, AssetMembership
from cadence.assets.errors import (
    AssetEvaluationUnavailableError,
    AssetNotFoundError,
    DuplicateAssetError,
    MarketDataUnavailableError,
    UnknownTickerError,
    UnsupportedCategoryError,
    UntradeableTickerError,
)
from cadence.assets.fundamentals import (
    FundamentalsProvider,
    SecEdgarFundamentalsProvider,
)
from cadence.assets.market_data import (
    MarketDataProvider,
    YFinanceMarketDataProvider,
)
from cadence.assets.models import AssetUniverseEvaluation
from cadence.assets.sector import Sector
from cadence.assets.universe_agent import (
    OpenAIUniverseEvaluationAgent,
    UniverseEvaluationAgent,
)
from cadence.broker import Broker, get_broker
from cadence.database import get_db

router = APIRouter(prefix="/assets", tags=["assets"])


def get_market_data_provider() -> MarketDataProvider:
    """Provide the market-data provider. Overridden with a fake in tests."""
    return YFinanceMarketDataProvider()


def get_universe_evaluation_agent() -> UniverseEvaluationAgent:
    """Provide the universe-evaluation agent. Overridden with a fake in tests."""
    return OpenAIUniverseEvaluationAgent()


def get_fundamentals_provider() -> FundamentalsProvider:
    """Provide the SEC EDGAR fundamentals provider. Overridden with a fake in tests."""
    return SecEdgarFundamentalsProvider()


DbSession = Annotated[Session, Depends(get_db)]
Provider = Annotated[MarketDataProvider, Depends(get_market_data_provider)]
BrokerDep = Annotated[Broker, Depends(get_broker)]
FundamentalsDep = Annotated[
    FundamentalsProvider, Depends(get_fundamentals_provider)
]
EvaluationAgentDep = Annotated[
    UniverseEvaluationAgent, Depends(get_universe_evaluation_agent)
]


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    db: DbSession,
    provider: Provider,
    broker: BrokerDep,
    fundamentals: FundamentalsDep,
) -> AssetRead:
    """Add an asset by ticker: enrich, classify, verify tradability, and persist.

    Stock assets also get their SEC EDGAR fundamentals fetched on creation
    (best-effort). A brokerage :class:`ConnectionError` (unconfigured/unreachable
    Alpaca) is handled globally and returned as 503; see ``create_app``.
    """
    try:
        asset = service.add_asset(
            db, payload.ticker, provider, broker, fundamentals=fundamentals
        )
    except DuplicateAssetError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except (
        UnknownTickerError,
        UnsupportedCategoryError,
        UntradeableTickerError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return AssetRead.model_validate(asset)


@router.post("/fundamentals/refresh", response_model=FundamentalsRefreshRead)
def refresh_fundamentals(
    db: DbSession,
    fundamentals: FundamentalsDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> FundamentalsRefreshRead:
    """Re-fetch SEC EDGAR fundamentals for every stock asset (quarterly cron).

    Guarded by the ``X-Cron-Token`` header. Runs the best-effort batch refresh
    synchronously and returns a summary of the run. Also serves as the one-time
    backfill for existing stocks (invoked once after deploy).
    """
    summary = service.refresh_stock_fundamentals(db, fundamentals)
    return FundamentalsRefreshRead.model_validate(summary)


# Allowed page sizes, kept in lockstep with the frontend selector.
ALLOWED_PAGE_SIZES = (20, 50, 100)
# Known instrument categories accepted by the category filter.
VALID_CATEGORIES = frozenset(member.value for member in AssetCategory)
# Known economic sectors accepted by the sector filter.
VALID_SECTORS = frozenset(member.value for member in Sector)
# Known membership buckets accepted by the membership filter.
VALID_MEMBERSHIPS = frozenset(member.value for member in AssetMembership)


@router.get("", response_model=AssetListResponse)
def list_assets(
    db: DbSession,
    limit: Annotated[
        int, Query(description="Page size: 20, 50, or 100")
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
    search: Annotated[
        str | None, Query(description="Filter by ticker or name")
    ] = None,
    sort: Annotated[
        str, Query(description="Sort field: ticker or name")
    ] = "ticker",
    direction: Annotated[
        str, Query(description="Sort direction: asc or desc")
    ] = "asc",
    category: Annotated[
        list[str] | None,
        Query(description="Filter by category (repeatable); empty = all"),
    ] = None,
    sector: Annotated[
        list[str] | None,
        Query(description="Filter by sector (repeatable); empty = all"),
    ] = None,
    membership: Annotated[
        str,
        Query(description="Bucket to list: 'universe' (default) or 'watchlist'"),
    ] = AssetMembership.UNIVERSE.value,
) -> AssetListResponse:
    """Return a sorted, filtered page of assets plus the matching total.

    Ordered by ``sort``/``direction`` (default ticker asc). ``search`` and the
    repeatable ``category`` and ``sector`` filters compose across the selected
    ``membership`` bucket (default the tradable universe; ``watchlist`` lists the
    emerging-companies watchlist).
    """
    if limit not in ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"limit must be one of {ALLOWED_PAGE_SIZES}",
        )
    if sort not in service.SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sort must be one of {service.SORT_FIELDS}",
        )
    if direction not in service.SORT_DIRECTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"direction must be one of {service.SORT_DIRECTIONS}",
        )
    if category:
        invalid = sorted(set(category) - VALID_CATEGORIES)
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown category values: {invalid}",
            )
    if sector:
        invalid_sectors = sorted(set(sector) - VALID_SECTORS)
        if invalid_sectors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown sector values: {invalid_sectors}",
            )
    if membership not in VALID_MEMBERSHIPS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"membership must be one of {sorted(VALID_MEMBERSHIPS)}",
        )
    membership_filter = AssetMembership(membership)
    items = [
        AssetRead.model_validate(asset)
        for asset in service.list_assets(
            db,
            limit=limit,
            offset=offset,
            search=search,
            sort=sort,
            direction=direction,
            categories=category,
            sectors=sector,
            membership=membership_filter,
        )
    ]
    total = service.count_assets(
        db,
        search=search,
        categories=category,
        sectors=sector,
        membership=membership_filter,
    )
    return AssetListResponse(items=items, total=total)


def _evaluation_response(
    evaluation: AssetUniverseEvaluation | None,
    outdated: bool,
) -> AssetUniverseEvaluationResponse:
    """Build the read envelope with the computed ``outdated`` flag.

    ``outdated`` is not a stored column (it is derived on read against the
    current universe), so the read model is built explicitly from the row plus
    the flag.
    """
    if evaluation is None:
        return AssetUniverseEvaluationResponse(evaluation=None)
    return AssetUniverseEvaluationResponse(
        evaluation=AssetUniverseEvaluationRead(
            narrative=evaluation.narrative,
            strengths=evaluation.strengths,
            concerns=evaluation.concerns,
            suggestions=evaluation.suggestions,
            generated_at=evaluation.generated_at,
            outdated=outdated,
        )
    )


@router.get("/universe-evaluation", response_model=AssetUniverseEvaluationResponse)
def get_universe_evaluation(
    db: DbSession,
    agent: EvaluationAgentDep,
) -> AssetUniverseEvaluationResponse:
    """Return the current universe evaluation with a freshly computed outdated flag.

    Lazy-fills on first read: when no evaluation exists and the universe is
    non-empty, one is generated and persisted. An empty universe returns a null
    evaluation and never calls the AI provider.
    """
    assets = service.get_universe_assets(db)
    if not assets:
        return _evaluation_response(None, outdated=False)

    evaluation = service.get_evaluation(db)
    if evaluation is None:
        try:
            evaluation = service.generate_evaluation(db, agent, assets)
        except AssetEvaluationUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            ) from exc
        # Freshly generated against the current universe, so never outdated.
        return _evaluation_response(evaluation, outdated=False)

    return _evaluation_response(
        evaluation, outdated=service.evaluation_outdated(evaluation, assets)
    )


@router.post(
    "/universe-evaluation/refresh",
    response_model=AssetUniverseEvaluationResponse,
)
def refresh_universe_evaluation(
    db: DbSession,
    agent: EvaluationAgentDep,
) -> AssetUniverseEvaluationResponse:
    """Regenerate and replace the universe evaluation on demand.

    Always regenerates against the current universe and returns the new
    evaluation as not outdated. An empty universe returns a null evaluation and
    never calls the AI provider.
    """
    assets = service.get_universe_assets(db)
    if not assets:
        return _evaluation_response(None, outdated=False)
    try:
        evaluation = service.generate_evaluation(db, agent, assets)
    except AssetEvaluationUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return _evaluation_response(evaluation, outdated=False)


@router.get("/{ticker}/details", response_model=AssetDetailRead)
def get_asset_details(
    ticker: str,
    db: DbSession,
    provider: Provider,
) -> AssetDetailRead:
    """Return an asset's details, refreshing the snapshot at most once a day."""
    try:
        result = service.get_asset_detail(db, ticker, provider)
    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except (UnknownTickerError, MarketDataUnavailableError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    asset = result.asset
    snapshot = result.snapshot
    return AssetDetailRead(
        ticker=asset.ticker,
        name=asset.name,
        category=asset.category,
        sector=asset.sector,
        exchange=asset.exchange,
        currency=snapshot.currency,
        current_price=snapshot.current_price,
        previous_close=snapshot.previous_close,
        short_description=snapshot.short_description,
        # Stable profile fields come from the asset; volumes from the snapshot.
        country=asset.country,
        city=asset.city,
        employees=asset.employees,
        website=asset.website,
        volume=snapshot.volume,
        avg_volume=snapshot.avg_volume,
        price_history=[
            AssetDetailHistoryPoint.model_validate(point)
            for point in snapshot.price_history
        ],
        snapshot_date=snapshot.snapshot_date,
        # Surface the asset's stored fundamentals when present; absent (null)
        # otherwise. Reading the relationship never triggers a fetch.
        fundamentals=(
            AssetFundamentalsRead.model_validate(asset.fundamentals)
            if asset.fundamentals is not None
            else None
        ),
    )


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: int, db: DbSession) -> Response:
    """Hard-delete an asset by id."""
    if not service.delete_asset(db, asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
