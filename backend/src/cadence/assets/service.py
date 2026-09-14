"""Assets service/repository: business logic and data access.

Routers stay thin and delegate here. All DB access for the assets domain lives
in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.expression import ColumnElement, UnaryExpression

from cadence.assets.category import SUPPORTED_CATEGORIES
from cadence.assets.errors import (
    AssetNotFoundError,
    DuplicateAssetError,
    UnsupportedCategoryError,
)
from cadence.assets.evaluation import EvaluationResult, evaluate
from cadence.assets.market_data import HistoryBar, MarketDataProvider
from cadence.assets.metrics import derive_metrics
from cadence.assets.models import Asset, AssetDailySnapshot


def normalize_ticker(ticker: str) -> str:
    """Canonicalize a ticker for storage and lookup."""
    return ticker.strip().upper()


def add_asset(
    session: Session,
    ticker: str,
    provider: MarketDataProvider,
) -> Asset:
    """Fetch, classify, convert, evaluate, and persist an asset.

    Raises:
        DuplicateAssetError: if the (normalized) ticker already exists.
        UnknownTickerError: if the provider has no data for the ticker.
        MarketDataUnavailableError: on provider/FX failure (nothing persisted).
        UnsupportedCategoryError: if the instrument's category is not tradeable
            (only stock and crypto are supported); nothing is persisted.
    """
    normalized = normalize_ticker(ticker)

    existing = session.execute(
        select(Asset).where(Asset.ticker == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateAssetError(f"Asset {normalized!r} already exists")

    # May raise UnknownTickerError / MarketDataUnavailableError before any
    # persistence, guaranteeing no partial rows.
    derived = derive_metrics(provider, normalized)

    # Only tradeable categories (stock, crypto) may enter the universe; reject
    # anything else before persistence so no untradeable row is ever stored.
    if derived.category not in SUPPORTED_CATEGORIES:
        raise UnsupportedCategoryError(
            f"Asset {normalized!r} has unsupported category "
            f"{derived.category.value!r}; only stock and crypto are supported"
        )

    result = evaluate(derived.metrics)

    asset = Asset(
        ticker=normalized,
        name=derived.name,
        category=derived.category.value,
        sector=derived.sector.value if derived.sector else None,
        exchange=derived.exchange,
        currency=derived.currency,
        country=derived.country,
        city=derived.city,
        employees=derived.employees,
        website=derived.website,
        market_cap_eur=derived.metrics.market_cap_eur,
        avg_daily_turnover_eur=derived.metrics.avg_daily_turnover_eur,
        history_years=derived.metrics.history_years,
        is_eligible=result.is_eligible,
        criteria_results=_serialize_criteria(result),
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


# Sortable columns exposed to the API, mapped to their model attribute.
SORT_FIELDS = ("ticker", "name")
SORT_DIRECTIONS = ("asc", "desc")


def _search_filter(search: str | None) -> ColumnElement[bool] | None:
    """Build a case-insensitive ticker/name substring filter for ``search``.

    Returns ``None`` when the query is empty/whitespace. LIKE metacharacters
    (``%``, ``_``, ``\\``) in the user input are escaped so they match
    literally rather than as wildcards.
    """
    if search is None:
        return None
    query = search.strip()
    if not query:
        return None
    escaped = (
        query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    pattern = f"%{escaped}%"
    return or_(
        Asset.ticker.ilike(pattern, escape="\\"),
        Asset.name.ilike(pattern, escape="\\"),
    )


def _filters(
    search: str | None,
    categories: list[str] | None,
    sectors: list[str] | None = None,
) -> list[ColumnElement[bool]]:
    """Build the combined WHERE conditions shared by list and count.

    Composes (AND) the escaped substring ``search`` with a category membership
    filter and a sector membership filter. An empty/``None`` ``categories`` or
    ``sectors`` means "all" for that dimension. A sector filter matches only
    rows whose sector is among the selected slugs, so null-sector rows are
    excluded whenever any sector is selected (``NULL NOT IN (...)``).
    """
    conditions: list[ColumnElement[bool]] = []
    search_condition = _search_filter(search)
    if search_condition is not None:
        conditions.append(search_condition)
    if categories:
        conditions.append(Asset.category.in_(categories))
    if sectors:
        conditions.append(Asset.sector.in_(sectors))
    return conditions


def _order_by(sort: str, direction: str) -> list[UnaryExpression[Any]]:
    """Build a stable, deterministic ORDER BY for the given sort/direction.

    ``ticker`` (unique, non-null) sorts by ticker then ``id``. ``name``
    (nullable, non-unique) sorts by name with NULLS LAST in both directions,
    then falls back to ticker and ``id`` so paging stays consistent. Unknown
    sort fields fall back to the default ticker order.
    """
    descending = direction == "desc"

    def ordered(column: InstrumentedAttribute[Any]) -> UnaryExpression[Any]:
        return column.desc() if descending else column.asc()

    if sort == "name":
        return [
            ordered(Asset.name).nulls_last(),
            ordered(Asset.ticker),
            ordered(Asset.id),
        ]
    return [ordered(Asset.ticker), ordered(Asset.id)]


def list_assets(
    session: Session,
    *,
    limit: int | None = None,
    offset: int = 0,
    search: str | None = None,
    sort: str = "ticker",
    direction: str = "asc",
    categories: list[str] | None = None,
    sectors: list[str] | None = None,
) -> list[Asset]:
    """Return stored assets in the requested order, optionally paged/filtered.

    ``search`` filters by ticker or instrument name (case-insensitive
    substring), ``categories`` restricts to the given instrument categories,
    and ``sectors`` restricts to the given economic sectors (empty/``None`` =
    all for each); all are applied across the whole universe and compose (AND).
    ``sort`` (``ticker``/``name``) and ``direction`` (``asc``/``desc``) order
    the result deterministically (default ``ticker asc``). ``limit``/``offset``
    page the ordered result; ``limit=None`` returns all matching rows.
    """
    stmt = select(Asset).order_by(*_order_by(sort, direction))
    for condition in _filters(search, categories, sectors):
        stmt = stmt.where(condition)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.execute(stmt).scalars())


def count_assets(
    session: Session,
    search: str | None = None,
    categories: list[str] | None = None,
    sectors: list[str] | None = None,
) -> int:
    """Count stored assets matching ``search``/``categories``/``sectors`` (all if unset)."""
    stmt = select(func.count()).select_from(Asset)
    for condition in _filters(search, categories, sectors):
        stmt = stmt.where(condition)
    return session.execute(stmt).scalar_one()


def delete_asset(session: Session, asset_id: int) -> bool:
    """Hard-delete an asset by id. Return whether it existed."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        return False
    session.delete(asset)
    session.commit()
    return True


@dataclass(frozen=True)
class AssetDetailResult:
    """The stored asset plus its snapshot for the requested day.

    Carries exactly what the API layer needs to build the details response,
    keeping the domain layer free of Pydantic.
    """

    asset: Asset
    snapshot: AssetDailySnapshot


def get_asset_detail(
    session: Session,
    ticker: str,
    provider: MarketDataProvider,
    today: date | None = None,
) -> AssetDetailResult:
    """Return the asset's detail snapshot for ``today``, fetching if needed.

    Serves an existing snapshot for the current calendar day without contacting
    the provider. Otherwise fetches fresh native-currency detail data, stores it
    as that day's snapshot, and returns it. Fetches at most once per calendar
    day per asset (guarded by the ``(asset_id, snapshot_date)`` unique key).

    Raises:
        AssetNotFoundError: if the (normalized) ticker is not stored.
        UnknownTickerError: propagated from the provider for unknown tickers.
        MarketDataUnavailableError: if a fresh fetch is required and fails. An
            older snapshot is never served in its place.
    """
    normalized = normalize_ticker(ticker)

    asset = session.execute(
        select(Asset).where(Asset.ticker == normalized)
    ).scalar_one_or_none()
    if asset is None:
        raise AssetNotFoundError(f"Asset {normalized!r} not found")

    reference_day = today or datetime.now(tz=UTC).date()

    existing = _select_snapshot(session, asset.id, reference_day)
    if existing is not None:
        return AssetDetailResult(asset=asset, snapshot=existing)

    # May raise UnknownTickerError / MarketDataUnavailableError before any
    # persistence; an older snapshot is deliberately not served on failure.
    detail = provider.fetch_detail(normalized)

    snapshot = AssetDailySnapshot(
        asset_id=asset.id,
        snapshot_date=reference_day,
        currency=asset.currency,
        current_price=detail.current_price,
        previous_close=detail.previous_close,
        short_description=detail.short_description,
        volume=detail.volume,
        avg_volume=detail.avg_volume,
        price_history=_serialize_history(detail.price_history),
    )
    session.add(snapshot)
    try:
        session.commit()
    except IntegrityError:
        # Concurrent request already inserted today's snapshot; adopt it.
        session.rollback()
        raced = _select_snapshot(session, asset.id, reference_day)
        if raced is None:
            raise
        return AssetDetailResult(asset=asset, snapshot=raced)

    session.refresh(snapshot)
    return AssetDetailResult(asset=asset, snapshot=snapshot)


def _select_snapshot(
    session: Session, asset_id: int, snapshot_date: date
) -> AssetDailySnapshot | None:
    return session.execute(
        select(AssetDailySnapshot).where(
            AssetDailySnapshot.asset_id == asset_id,
            AssetDailySnapshot.snapshot_date == snapshot_date,
        )
    ).scalar_one_or_none()


def _serialize_history(history: list[HistoryBar]) -> list[dict[str, Any]]:
    return [
        {"date": bar.date.isoformat(), "close": float(bar.close)}
        for bar in history
    ]


def _serialize_criteria(result: EvaluationResult) -> list[dict[str, Any]]:
    return [
        {
            "name": criterion.name,
            "passed": criterion.passed,
            "value": criterion.value,
            "threshold": criterion.threshold,
        }
        for criterion in result.criteria
    ]
