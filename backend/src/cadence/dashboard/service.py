"""Service layer computing the dashboard's overview metrics live.

All metrics are derived from the current rows with cheap aggregate queries and by
reusing the existing domain service functions (``count_assets``,
``count_portfolios``, ``count_sessions``) rather than duplicating their SQL.
Nothing is cached or persisted; the universe is small, so a full aggregate per
request is fast.

"Report over what exists": no asset is excluded for missing an optional field.
Assets with no ``sector`` are grouped under the sentinel key ``"no sector"``
rather than being dropped from the breakdown, and every metric is well-defined on
an empty database (zeros and empty lists, never an error).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from cadence.assets import service as assets_service
from cadence.assets.models import Asset
from cadence.assets.sector import Sector
from cadence.paper_trading import service as paper_trading_service
from cadence.paper_trading.constants import SessionStatus
from cadence.paper_trading.models import PaperTrade
from cadence.portfolios import service as portfolios_service
from cadence.recommendations.composition import (
    CompositionEntry,
    UniverseComposition,
)

# Sentinel bucket keys for assets whose optional grouping field is absent.
NO_SECTOR_KEY = "no sector"
UNKNOWN_COUNTRY_KEY = "unknown"

# A trade counts as "recent" when executed within this many days of now.
RECENT_TRADE_WINDOW_DAYS = 7


@dataclass(frozen=True)
class BreakdownEntry:
    """One group of a breakdown: a grouping key and its asset count."""

    key: str
    count: int


@dataclass(frozen=True)
class AssetUniverseMetrics:
    """Universe size and composition.

    ``by_category`` and ``by_sector`` are ordered by descending count then key.
    ``by_sector`` reports only sectors that actually have assets (including the
    ``"no sector"`` bucket when any asset lacks one); absent sectors are omitted.
    """

    total: int
    eligible: int
    ineligible: int
    by_category: list[BreakdownEntry] = field(default_factory=list)
    by_sector: list[BreakdownEntry] = field(default_factory=list)


@dataclass(frozen=True)
class PaperTradingMetrics:
    """Paper-trading activity: active sessions and recently executed trades."""

    active_sessions: int
    recent_trades: int


@dataclass(frozen=True)
class DashboardMetrics:
    """The full dashboard overview computed over the current data."""

    assets: AssetUniverseMetrics
    portfolio_count: int
    paper_trading: PaperTradingMetrics


def _breakdown(
    session: Session,
    column: InstrumentedAttribute[str | None],
    *,
    null_key: str | None = None,
) -> list[BreakdownEntry]:
    """Count assets grouped by ``column``, ordered by descending count then key.

    When ``null_key`` is given, NULL values are coalesced to that sentinel key so
    an absent value becomes an explicit bucket instead of being omitted; when it
    is ``None``, NULL groups are skipped. The column is cast to text first so
    enum-typed columns yield plain string keys and a string sentinel can be
    coalesced in without tripping the enum's value validation.
    """
    text_column = cast(column, String)
    key_expr = (
        func.coalesce(text_column, null_key) if null_key is not None else text_column
    )
    count_expr = func.count(Asset.id)
    stmt = (
        select(key_expr, count_expr)
        .group_by(key_expr)
        .order_by(count_expr.desc(), key_expr.asc())
    )
    return [
        BreakdownEntry(key=key, count=count)
        for key, count in session.execute(stmt).all()
        if key is not None
    ]


def get_universe_composition(session: Session) -> UniverseComposition:
    """Summarize how the current universe is distributed by sector and country.

    The sector list covers *every* :class:`Sector` — those with no assets appear
    with a zero count so absent sectors are visible to the recommender — plus the
    ``"no sector"`` bucket when any asset lacks one. Countries are present-only
    (with the ``"unknown"`` bucket for assets missing one), since they are not
    drawn from a fixed set. Both are ordered by descending count, then key.
    Shared by the recommender and the dashboard so the universe is bucketed in
    exactly one place.
    """
    total = session.execute(select(func.count(Asset.id))).scalar_one()

    present_sectors = _breakdown(session, Asset.sector, null_key=NO_SECTOR_KEY)
    present_keys = {entry.key for entry in present_sectors}
    sector_entries = [
        CompositionEntry(key=entry.key, count=entry.count) for entry in present_sectors
    ]
    # Surface every enum sector, including absent ones, as an explicit zero.
    sector_entries.extend(
        CompositionEntry(key=member.value, count=0)
        for member in Sector
        if member.value not in present_keys
    )
    sector_entries.sort(key=lambda entry: (-entry.count, entry.key))

    country_entries = tuple(
        CompositionEntry(key=entry.key, count=entry.count)
        for entry in _breakdown(session, Asset.country, null_key=UNKNOWN_COUNTRY_KEY)
    )

    return UniverseComposition(
        total=total,
        sectors=tuple(sector_entries),
        countries=country_entries,
    )


def _asset_universe_metrics(session: Session) -> AssetUniverseMetrics:
    """Compute universe size, eligibility split, and category/sector breakdowns."""
    total = assets_service.count_assets(session)
    eligible = session.execute(
        select(func.count(Asset.id)).where(Asset.is_eligible.is_(True))
    ).scalar_one()

    # Reuse the shared composition for sectors (one source of truth), dropping
    # the zero-filled absent sectors the recommender needs but the overview does
    # not. Categories have no shared aggregate, so group them directly.
    composition = get_universe_composition(session)
    by_sector = [
        BreakdownEntry(key=entry.key, count=entry.count)
        for entry in composition.sectors
        if entry.count > 0
    ]
    return AssetUniverseMetrics(
        total=total,
        eligible=eligible,
        ineligible=total - eligible,
        by_category=_breakdown(session, Asset.category),
        by_sector=by_sector,
    )


def _paper_trading_metrics(session: Session) -> PaperTradingMetrics:
    """Count active sessions and trades executed within the recent window."""
    active_sessions = paper_trading_service.count_sessions(
        session, status=SessionStatus.ACTIVE
    )
    cutoff = datetime.now(tz=UTC) - timedelta(days=RECENT_TRADE_WINDOW_DAYS)
    recent_trades = session.execute(
        select(func.count(PaperTrade.id)).where(PaperTrade.executed_at >= cutoff)
    ).scalar_one()
    return PaperTradingMetrics(
        active_sessions=active_sessions,
        recent_trades=recent_trades,
    )


def get_dashboard_metrics(session: Session) -> DashboardMetrics:
    """Compute the full dashboard overview over the current data.

    Succeeds on an empty database, returning zero counts and empty breakdowns.
    """
    return DashboardMetrics(
        assets=_asset_universe_metrics(session),
        portfolio_count=portfolios_service.count_portfolios(session),
        paper_trading=_paper_trading_metrics(session),
    )
