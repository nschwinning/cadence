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

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from cadence.ai_portfolio import service as ai_portfolio_service
from cadence.ai_portfolio.constants import EventStatus, EventType
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.assets import service as assets_service
from cadence.assets.category import AssetCategory
from cadence.assets.models import Asset
from cadence.assets.sector import Sector
from cadence.broker.base import Broker
from cadence.config import settings
from cadence.dashboard.constants import (
    PERFORMERS_LIMIT,
    REBALANCE_CRON_SLOTS_ET,
    RECENT_ACTIVITY_LIMIT,
    DashboardRange,
    resolve_range_start,
)
from cadence.paper_trading import service as paper_trading_service
from cadence.paper_trading.benchmark import (
    Contribution,
    load_benchmark_series,
    rebased_benchmark_value,
)
from cadence.paper_trading.constants import (
    Benchmark,
    SessionStatus,
    benchmark_display_name,
)
from cadence.paper_trading.models import PaperTrade, PaperTradingSession
from cadence.portfolios import service as portfolios_service
from cadence.price_history import service as price_history_service
from cadence.recommendations.composition import (
    CompositionEntry,
    UniverseComposition,
)

# US/Eastern — the timezone of the fixed rebalance cron slots used to
# approximate the automation panel's next scheduled run.
_EASTERN = ZoneInfo("America/New_York")

# Upper bound on sessions pulled into the overview; comfortably above any real
# session count so the aggregate is never silently truncated by the list default.
_OVERVIEW_SESSION_LIMIT = 1000

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


# --------------------------------------------------------------------------- #
# Range-scoped overview                                                        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SessionValuePoint:
    """One (date, value) point of a session's value series, windowed to a range."""

    date: date
    value: float


@dataclass(frozen=True)
class SessionContribution:
    """One capital contribution to a session: its amount and effective date.

    The session's opening capital (effective at its start date) plus any later
    capital-increase events. The client combines these with each benchmark index's
    prices to build a buy-and-hold benchmark line that invests each contribution in
    the index on its effective date and holds, summed across the selected sessions.
    """

    effective_date: date
    amount: float


@dataclass(frozen=True)
class SessionPerformance:
    """A single active session's range-scoped performance data.

    ``current_value`` is the live net-asset value; ``pnl`` is the value now minus
    the value at the range start (the latest snapshot on/before the start, or the
    allocated capital when the session began within the range or for ``Max``);
    ``fees`` are the per-trade transaction costs incurred within the range.
    ``realised_pnl`` and ``unrealised_pnl`` are the range-relative money triple
    partners of ``current_value``: ``realised_pnl`` is the summed closed-lot
    realised P&L for lots closed within the range (equal to the cumulative realised
    P&L for ``Max``), and ``unrealised_pnl`` is the current live unrealised P&L
    minus the unrealised P&L captured in the range-start snapshot (equal to the live
    unrealised P&L for ``Max`` or when no range-start snapshot exists). They are two
    independent figures, not an additive decomposition of ``pnl``.
    ``points`` is the value series windowed to the range (oldest first), which the
    client sums across the selected sessions and re-aggregates on selection
    changes without re-fetching. ``contributions`` is the session's opening capital
    plus later capital increases, which the client aggregates into the benchmark
    comparison line (not windowed — the full set is needed to value the buy-and-hold).
    ``benchmark_value`` is the since-inception, range-independent current USD value of
    a contribution-aware buy-and-hold of ``contributions`` in the session's own
    benchmark (``None`` when unpriceable), which the client aggregates into the live
    excess-return tile.
    """

    id: uuid.UUID
    label: str
    allocated_capital: float
    current_value: float
    pnl: float
    realised_pnl: float
    unrealised_pnl: float
    fees: float
    points: list[SessionValuePoint]
    contributions: list[SessionContribution]
    benchmark_value: float | None


@dataclass(frozen=True)
class AutomationRun:
    """A reference to a single AI run for the automation summary."""

    id: uuid.UUID
    event_type: str
    status: str
    created_at: datetime
    session_id: uuid.UUID | None


@dataclass(frozen=True)
class AutomationSummary:
    """Health of the AI rebalance automation, scoped to the selected range.

    ``next_run_approx`` is derived arithmetically from the fixed daily rebalance
    cron slots and is always flagged ``approximate`` (it ignores market holidays).
    """

    latest_run: AutomationRun | None
    in_flight: bool
    failed_in_range: int
    next_run_approx: datetime
    next_run_is_approximate: bool


@dataclass(frozen=True)
class ActivityEntry:
    """One AI run in the recent-activity feed."""

    id: uuid.UUID
    session_id: uuid.UUID | None
    session_label: str | None
    kind: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class UniverseBalance:
    """Current composition of the asset universe (range-independent)."""

    total: int
    eligible: int
    ineligible: int
    sectors_count: int
    top_sector_key: str | None
    top_sector_share: float
    top_category_key: str | None
    top_category_share: float


@dataclass(frozen=True)
class PerformerEntry:
    """One asset's market return over the range, for the performer rankings."""

    asset_id: int
    ticker: str
    name: str | None
    return_pct: float


@dataclass(frozen=True)
class UniversePerformers:
    """Best and worst tracked assets by market return over the range."""

    best: list[PerformerEntry]
    worst: list[PerformerEntry]


@dataclass(frozen=True)
class BenchmarkPricePoint:
    """One (date, price) point of a benchmark index's closing-price series."""

    date: date
    price: float


@dataclass(frozen=True)
class BenchmarkOverlaySeries:
    """One catalog benchmark's price series for the combined-equity overlay.

    ``points`` carries the index's stored closes over the plotted era as raw
    (date, price) pairs — *not* pre-converted to any portfolio-relative dollars.
    The client combines these prices with the selected sessions' contributions to
    build a buy-and-hold dollar line (each session's contributed capital invested in
    the index at each contribution's effective date, held, summed over the selected
    sessions), so the line depends on the current session selection. An index with
    no stored prices in range has an empty ``points`` list rather than being omitted.
    """

    benchmark_id: str
    name: str
    points: list[BenchmarkPricePoint]


@dataclass(frozen=True)
class DashboardOverview:
    """The full range-scoped dashboard overview payload."""

    range: DashboardRange
    sessions: list[SessionPerformance]
    automation: AutomationSummary
    recent_activity: list[ActivityEntry]
    universe_balance: UniverseBalance
    universe_performers: UniversePerformers
    benchmark_series: list[BenchmarkOverlaySeries]


def _range_start_datetime(start_date: date | None) -> datetime | None:
    """The inclusive UTC datetime at the start of ``start_date`` (``None`` = Max)."""
    if start_date is None:
        return None
    return datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC)


def _range_fees(
    session: Session, session_id: uuid.UUID, start_dt: datetime | None
) -> float:
    """Asset-class-aware transaction cost incurred by a session within the range.

    Under the asset-class-aware fee model equities are free and crypto is charged
    :data:`settings.CRYPTO_FEE_PCT` of notional, so the range fee is
    ``CRYPTO_FEE_PCT`` times the summed notional of the *crypto* trades executed
    on/after the range start (all trades for ``Max``). A trade is crypto iff its
    ticker joins to an :class:`Asset` whose category is crypto; equity trades
    contribute zero. This uses the stored ``notional`` (``quantity * price``); the
    tiny filled-vs-quoted difference is acceptable for a projection.
    """
    stmt = (
        select(func.coalesce(func.sum(PaperTrade.notional), 0.0))
        .select_from(PaperTrade)
        .join(Asset, Asset.ticker == PaperTrade.ticker)
        .where(
            PaperTrade.session_id == session_id,
            Asset.category == AssetCategory.CRYPTO.value,
        )
    )
    if start_dt is not None:
        stmt = stmt.where(PaperTrade.executed_at >= start_dt)
    crypto_notional = session.execute(stmt).scalar_one()
    return crypto_notional * settings.CRYPTO_FEE_PCT


def _session_performance(
    session: Session,
    *,
    session_row: PaperTradingSession,
    broker: Broker,
    start_date: date | None,
    start_dt: datetime | None,
    today: date,
) -> SessionPerformance:
    """Build one active session's range-scoped performance data."""
    history = paper_trading_service.list_value_history(
        session, session_id=session_row.id
    )
    allocated = session_row.allocated_capital

    kpis = paper_trading_service.session_kpis(
        session, session_id=session_row.id, broker=broker
    )
    current_value = kpis.current_value

    # Contributions drive the live value-band tiles and the client-side benchmark
    # overlay: the opening capital plus any later capital increases. The baseline is
    # anchored at the session's first snapshot date, or — before any snapshot exists
    # (a freshly built session, between its build and its first snapshot cron) — at the
    # dashboard's as-of date, so the session always reports its contributed capital and
    # its fresh cash is never mistaken for profit (which would otherwise inflate the
    # lifetime P&L and total-return tiles by the whole allocation). NOT windowed to the
    # range: earlier contributions are still held within it.
    contrib_start = history[0].snapshot.snapshot_date if history else today
    events = paper_trading_service.list_capital_events(
        session, session_id=session_row.id
    )
    contributions = [
        SessionContribution(effective_date=c.effective_date, amount=c.amount)
        for c in paper_trading_service.session_contributions(
            session_row, events, start_date=contrib_start
        )
    ]

    # Value series windowed to the range (oldest first). A session with no snapshot yet
    # has no stored points, so it would be invisible on the combined-equity line while
    # its contributed capital already feeds the benchmark line — leaving the two lines
    # misaligned. Anchor a single live point (current value, at the as-of date) so the
    # equity line reflects the session's current all-cash value and stays aligned with
    # the benchmark overlay until the first real snapshot lands.
    if history:
        points = [
            SessionValuePoint(
                date=point.snapshot.snapshot_date, value=point.snapshot.total_value
            )
            for point in history
            if start_date is None or point.snapshot.snapshot_date >= start_date
        ]
    else:
        points = [SessionValuePoint(date=today, value=current_value)]

    # Value at the range start: the latest snapshot on/before the start date. A
    # session with no snapshot before the start began within the range, so its
    # baseline is its allocated capital (which is also the Max baseline).
    if start_date is None:
        value_start = allocated
    else:
        prior = [
            point.snapshot.total_value
            for point in history
            if point.snapshot.snapshot_date <= start_date
        ]
        value_start = prior[-1] if prior else allocated
    pnl = current_value - value_start

    # Range-relative money triple partners of current_value: realised from the
    # closed lots whose exit falls in the range (cumulative total_pnl for Max), and
    # unrealised as the live mark-to-market minus the range-start snapshot baseline
    # (live unrealised for Max or when no range-start snapshot exists).
    realised_pnl = paper_trading_service.range_realised_pnl(
        session, session_row.id, start=start_dt
    )
    unrealised_pnl = paper_trading_service.range_unrealised_pnl(
        session,
        session_row.id,
        start_date=start_date,
        current_unrealised=kpis.unrealised_pnl,
    )

    # Since-inception, range-independent current value of a contribution-aware
    # buy-and-hold of the session's contributions in its own benchmark, for the live
    # excess-return tile. This is the money-weighted basis the combined-equity overlay
    # uses (rebased_benchmark_value) — deliberately NOT the time-weighted basis of the
    # session-detail excess KPI (benchmark_return_fraction) — so it matches the
    # money-weighted total return the client derives. None when unpriceable or there
    # are no contributions yet.
    benchmark_value: float | None = None
    if contributions:
        benchmark_value = rebased_benchmark_value(
            load_benchmark_series(session, session_row.benchmark),
            contributions=[
                Contribution(effective_date=c.effective_date, amount=c.amount)
                for c in contributions
            ],
            as_of=today,
        )

    return SessionPerformance(
        id=session_row.id,
        label=session_row.portfolio_name or session_row.strategy_key,
        allocated_capital=allocated,
        current_value=current_value,
        pnl=pnl,
        realised_pnl=realised_pnl,
        unrealised_pnl=unrealised_pnl,
        fees=_range_fees(session, session_row.id, start_dt),
        points=points,
        contributions=contributions,
        benchmark_value=benchmark_value,
    )


def _next_rebalance_run(now: datetime) -> datetime:
    """Approximate next rebalance run time from the fixed ET cron slots.

    Returns the next slot strictly after ``now`` in US/Eastern — later today if one
    remains, otherwise the first slot tomorrow — as a UTC datetime. Market holidays
    are ignored (the value is flagged approximate).
    """
    now_et = now.astimezone(_EASTERN)
    for hour, minute in REBALANCE_CRON_SLOTS_ET:
        candidate = now_et.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate > now_et:
            return candidate.astimezone(UTC)
    first_hour, first_minute = REBALANCE_CRON_SLOTS_ET[0]
    tomorrow = (now_et + timedelta(days=1)).replace(
        hour=first_hour, minute=first_minute, second=0, microsecond=0
    )
    return tomorrow.astimezone(UTC)


def _automation_summary(
    session: Session,
    *,
    active_sessions: list[PaperTradingSession],
    start_dt: datetime | None,
    now: datetime,
) -> AutomationSummary:
    """Summarize the AI rebalance automation's health over the range."""
    latest_runs = ai_portfolio_service.list_ai_runs(
        session, event_type=EventType.REBALANCE, limit=1
    )
    latest = latest_runs[0] if latest_runs else None
    latest_run = (
        AutomationRun(
            id=latest.id,
            event_type=latest.event_type,
            status=latest.status,
            created_at=latest.created_at,
            session_id=latest.session_id,
        )
        if latest is not None
        else None
    )

    in_flight = any(
        ai_portfolio_service.get_inflight_rebalance_event(session, row.id) is not None
        for row in active_sessions
    )

    failed_stmt = select(func.count(AIPortfolioEvent.id)).where(
        AIPortfolioEvent.status == EventStatus.FAILED.value
    )
    if start_dt is not None:
        failed_stmt = failed_stmt.where(AIPortfolioEvent.created_at >= start_dt)
    failed_in_range = session.execute(failed_stmt).scalar_one()

    return AutomationSummary(
        latest_run=latest_run,
        in_flight=in_flight,
        failed_in_range=failed_in_range,
        next_run_approx=_next_rebalance_run(now),
        next_run_is_approximate=True,
    )


def _recent_activity(
    session: Session,
    *,
    start_dt: datetime | None,
    label_map: dict[uuid.UUID, str],
) -> list[ActivityEntry]:
    """The most recent AI runs within the range, newest first, capped."""
    stmt = select(AIPortfolioEvent).order_by(
        AIPortfolioEvent.created_at.desc(), AIPortfolioEvent.id.desc()
    )
    if start_dt is not None:
        stmt = stmt.where(AIPortfolioEvent.created_at >= start_dt)
    events = session.execute(stmt.limit(RECENT_ACTIVITY_LIMIT)).scalars().all()
    return [
        ActivityEntry(
            id=event.id,
            session_id=event.session_id,
            session_label=(
                label_map.get(event.session_id)
                if event.session_id is not None
                else None
            ),
            kind=event.event_type,
            status=event.status,
            created_at=event.created_at,
        )
        for event in events
    ]


def _universe_balance(session: Session) -> UniverseBalance:
    """Current universe composition (eligibility split, sector/category shares)."""
    total = assets_service.count_assets(session)
    eligible = session.execute(
        select(func.count(Asset.id)).where(Asset.is_eligible.is_(True))
    ).scalar_one()
    sectors = _breakdown(session, Asset.sector, null_key=NO_SECTOR_KEY)
    categories = _breakdown(session, Asset.category)
    top_sector = sectors[0] if sectors else None
    top_category = categories[0] if categories else None
    return UniverseBalance(
        total=total,
        eligible=eligible,
        ineligible=total - eligible,
        sectors_count=len(sectors),
        top_sector_key=top_sector.key if top_sector else None,
        top_sector_share=(top_sector.count / total) if top_sector and total else 0.0,
        top_category_key=top_category.key if top_category else None,
        top_category_share=(
            top_category.count / total if top_category and total else 0.0
        ),
    )


def _universe_performers(
    session: Session, *, range_: DashboardRange, today: date
) -> UniversePerformers:
    """Rank tracked assets by market return over the range (best/worst)."""
    entries: list[PerformerEntry] = []
    for asset in assets_service.list_assets(session):
        return_pct = price_history_service.asset_return(
            session, asset_id=asset.id, range_=range_, today=today
        )
        if return_pct is None:
            continue
        entries.append(
            PerformerEntry(
                asset_id=asset.id,
                ticker=asset.ticker,
                name=asset.name,
                return_pct=return_pct,
            )
        )
    best = sorted(entries, key=lambda e: e.return_pct, reverse=True)[:PERFORMERS_LIMIT]
    worst = sorted(entries, key=lambda e: e.return_pct)[:PERFORMERS_LIMIT]
    return UniversePerformers(best=best, worst=worst)


def _benchmark_overlays(
    session: Session, *, floor: date | None
) -> list[BenchmarkOverlaySeries]:
    """Per-index price series for the combined-equity benchmark overlay.

    Returns one entry per catalog benchmark, in catalog order, each carrying the
    index's stored closes over the plotted era as raw (date, price) points. The
    series is windowed to ``floor`` — the earliest date across the sessions'
    range-windowed value series *and* their contribution effective dates — so it
    spans where the sessions are plotted yet always reaches back far enough to
    price the earliest contribution (a session that opened before the range start
    contributes earlier than its earliest windowed point). This keeps every
    contribution priceable so none is dropped from the client's benchmark line,
    while the ``Max`` range still ships no decades of pre-session history. The last
    close strictly *before* ``floor`` is prepended as a rebasing anchor so the
    client can resolve the benchmark price on or before the combined curve's start
    even when that start falls on a non-trading day. A benchmark with no stored
    prices in range yields an empty ``points`` list rather than being omitted;
    ``floor`` is ``None`` only when no session has any plotted point, in which case
    every series is empty.
    """
    overlays: list[BenchmarkOverlaySeries] = []
    for benchmark in Benchmark:
        points: list[BenchmarkPricePoint] = []
        if floor is not None:
            series = load_benchmark_series(session, benchmark.value)
            anchor: BenchmarkPricePoint | None = None
            for point_date, close in zip(series.dates, series.closes, strict=True):
                if point_date < floor:
                    # Keep only the latest pre-floor close as the rebasing anchor.
                    anchor = BenchmarkPricePoint(date=point_date, price=close)
                else:
                    points.append(BenchmarkPricePoint(date=point_date, price=close))
            if anchor is not None:
                points.insert(0, anchor)
        overlays.append(
            BenchmarkOverlaySeries(
                benchmark_id=benchmark.value,
                name=benchmark_display_name(benchmark),
                points=points,
            )
        )
    return overlays


def get_dashboard_overview(
    session: Session,
    *,
    range_: DashboardRange,
    broker: Broker,
    today: date | None = None,
    now: datetime | None = None,
) -> DashboardOverview:
    """Compute the range-scoped overview over the active paper-trading sessions.

    Aggregates per-session performance (series + range pnl/fees), the AI-automation
    summary, recent activity, the range-independent universe balance, and the
    best/worst performers over the range. Succeeds on an empty system, returning
    empty collections and zeroed aggregates rather than raising.
    """
    today = today or datetime.now(tz=UTC).date()
    now = now or datetime.now(tz=UTC)
    start_date = resolve_range_start(range_, today=today)
    start_dt = _range_start_datetime(start_date)

    active_sessions = paper_trading_service.list_sessions(
        session, status=SessionStatus.ACTIVE, limit=_OVERVIEW_SESSION_LIMIT
    )
    sessions = [
        _session_performance(
            session,
            session_row=row,
            broker=broker,
            start_date=start_date,
            start_dt=start_dt,
            today=today,
        )
        for row in active_sessions
    ]

    label_map = {
        row.id: (row.portfolio_name or row.strategy_key)
        for row in paper_trading_service.list_sessions(
            session, include_archived=True, limit=_OVERVIEW_SESSION_LIMIT
        )
    }

    # Benchmark overlay spans the plotted session era, floored early enough to
    # price every session contribution: the earliest date across the sessions'
    # windowed value series AND every session's contribution effective dates
    # (``None`` when nothing is plotted, which yields empty series). A session that
    # opened before the range start has a contribution earlier than its earliest
    # windowed point; without folding contribution dates in, that contribution
    # would fall before the overlay's anchor and be dropped from the benchmark line.
    session_point_dates = [point.date for perf in sessions for point in perf.points]
    contribution_dates = [
        contribution.effective_date
        for perf in sessions
        for contribution in perf.contributions
    ]
    overlay_floor = min([*session_point_dates, *contribution_dates], default=None)

    return DashboardOverview(
        range=range_,
        sessions=sessions,
        automation=_automation_summary(
            session,
            active_sessions=active_sessions,
            start_dt=start_dt,
            now=now,
        ),
        recent_activity=_recent_activity(
            session, start_dt=start_dt, label_map=label_map
        ),
        universe_balance=_universe_balance(session),
        universe_performers=_universe_performers(
            session, range_=range_, today=today
        ),
        benchmark_series=_benchmark_overlays(session, floor=overlay_floor),
    )
