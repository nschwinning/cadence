"""Pydantic v2 response/request schemas for the API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cadence.assets.category import AssetScope
from cadence.paper_trading.constants import Benchmark
from cadence.portfolios.constants import PortfolioSource, RiskProfile


class ServiceStatus(str, Enum):
    """Overall service health status."""

    OK = "ok"
    DEGRADED = "degraded"


class DatabaseStatus(str, Enum):
    """Database connectivity status."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class HealthResponse(BaseModel):
    """Health check payload. Always returned with HTTP 200."""

    status: ServiceStatus
    database: DatabaseStatus


class AssetCreate(BaseModel):
    """Request body for adding an asset by ticker."""

    ticker: str = Field(..., min_length=1, description="Ticker symbol, e.g. AAPL")


class CriterionResult(BaseModel):
    """Outcome of a single eligibility criterion."""

    name: str
    passed: bool
    value: float | None
    threshold: float


class AssetRead(BaseModel):
    """Full snapshot of a stored asset, including its eligibility breakdown."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str | None
    alpaca_symbol: str | None = None
    category: str
    sector: str | None
    exchange: str | None
    currency: str
    market_cap_usd: float | None
    avg_daily_turnover_usd: float | None
    history_years: float | None
    is_eligible: bool
    criteria_results: list[CriterionResult]
    created_at: datetime


class AssetListResponse(BaseModel):
    """A page of stored assets plus the total number matching the query.

    ``items`` is the current bounded page (newest first); ``total`` is the count
    of all assets matching the active search, so the client can drive infinite
    scroll and show progress ("Showing X of N").
    """

    items: list[AssetRead]
    total: int


class AssetDetailHistoryPoint(BaseModel):
    """A single point on the asset details price-history chart."""

    date: date
    close: float


class AssetDetailRead(BaseModel):
    """Asset details view: core facts plus a native-currency price history.

    The ``country``/``city``/``employees``/``website``/``volume``/``avg_volume``
    fields back the Company Information panel; each is optional and served as
    ``null`` when the provider did not supply it. ``exchange`` and ``currency``
    are also surfaced in that panel.
    """

    ticker: str
    name: str | None
    category: str
    sector: str | None
    exchange: str | None
    currency: str
    current_price: float | None
    previous_close: float | None
    short_description: str | None
    country: str | None
    city: str | None
    employees: int | None
    website: str | None
    volume: int | None
    avg_volume: int | None
    price_history: list[AssetDetailHistoryPoint]
    snapshot_date: date


class RecommendationRunCreate(BaseModel):
    """Request body for starting an asset-recommendation run."""

    count: int = Field(
        ..., ge=1, description="How many new assets to add, upper bound"
    )
    categories: list[str] = Field(
        ..., min_length=1, description="Asset categories to restrict candidates to"
    )


class RecommendationCandidateResult(BaseModel):
    """Per-candidate outcome recorded on a run."""

    ticker: str
    outcome: str
    detail: str | None = None


class RecommendationRunRead(BaseModel):
    """A recommendation run: request, status, per-candidate results, and errors."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    status: str
    requested_count: int
    requested_categories: list[str]
    prompt: str | None
    tool_call_count: int
    results: list[RecommendationCandidateResult]
    error: str | None


# --------------------------------------------------------------------------- #
# Portfolios
# --------------------------------------------------------------------------- #


class PortfolioCreate(BaseModel):
    """Request body for creating a portfolio."""

    name: str = Field(..., min_length=1, description="Human-readable portfolio name")
    stocks: list[str] = Field(
        ..., min_length=1, description="Tickers (normalized server-side)"
    )
    source: PortfolioSource = Field(
        default=PortfolioSource.MANUAL, description="How the portfolio was created"
    )
    description: str | None = Field(default=None, description="Optional notes")
    risk_profile: RiskProfile | None = Field(
        default=None, description="Optional risk appetite"
    )
    max_allocation_pct: float = Field(
        default=1.0,
        gt=0,
        le=1.0,
        description="Per-position allocation cap in (0, 1]",
    )
    source_run_id: str | None = Field(
        default=None, description="Provenance link (e.g. a recommendation run id)"
    )


class PortfolioStocksUpdate(BaseModel):
    """Request body for replacing a portfolio's ticker list."""

    stocks: list[str] = Field(
        ..., min_length=1, description="New tickers (normalized server-side)"
    )


class PortfolioRead(BaseModel):
    """A stored portfolio."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    stocks: list[str]
    max_allocation_pct: float
    source: str
    risk_profile: str | None
    source_run_id: str | None
    created_at: datetime
    archived_at: datetime | None


class PortfolioListResponse(BaseModel):
    """A list of stored portfolios plus the total number matching the query."""

    items: list[PortfolioRead]
    total: int


# --------------------------------------------------------------------------- #
# Paper trading (read-only)
# --------------------------------------------------------------------------- #


class PaperTradingSessionRead(BaseModel):
    """A paper-trading session and its running totals."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    portfolio_name: str | None
    strategy_key: str
    status: str
    allocated_capital: float
    max_allocation_pct: float
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None
    total_trades: int
    total_pnl: float
    session_metadata: dict[str, Any] | None
    schedule_mode: str
    archived_at: datetime | None
    # The rebalance-prompt version frozen onto this session at build time.
    rebalance_prompt_version: int
    # The benchmark index this session is compared against (a catalog id).
    benchmark: str


class PaperTradingSessionListResponse(BaseModel):
    """A list of paper-trading sessions plus the matching total."""

    items: list[PaperTradingSessionRead]
    total: int


class PaperTradeRead(BaseModel):
    """A single recorded paper trade (fill)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    ai_portfolio_event_id: uuid.UUID | None
    ticker: str
    side: str
    quantity: float
    price: float
    notional: float
    signal_type: str
    executed_at: datetime
    order_id: str | None
    order_status: str
    filled_price: float | None
    filled_at: datetime | None


class PaperTradeListResponse(BaseModel):
    """A list of paper trades plus the matching total."""

    items: list[PaperTradeRead]
    total: int


class PaperTradeReconcileRead(BaseModel):
    """Result of reconciling one session's non-terminal orders.

    Carries the per-run counts plus the session's refreshed trades so the client
    can render the updated statuses without a second round-trip.
    """

    trades_seen: int
    trades_reconciled: int
    trades_filled: int
    trades_basis_corrected: int
    trades: list[PaperTradeRead]


class AIDailyReconcileResponse(BaseModel):
    """Aggregate result of the scheduled cross-session reconciliation."""

    sessions_reconciled: int
    trades_reconciled: int


class SessionRunRead(BaseModel):
    """A record of a single session run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    run_at: datetime
    signals_scanned: int
    signals_actionable: int
    orders_executed: int
    orders_skipped: int
    details: list[dict[str, Any]] | None
    status: str
    run_trigger: str
    duration_ms: int | None


class SessionRunListResponse(BaseModel):
    """A list of session runs plus the matching total."""

    items: list[SessionRunRead]
    total: int


class ClosedPositionRead(BaseModel):
    """A closed position with realized P&L."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    ai_portfolio_event_id: uuid.UUID | None
    ticker: str
    quantity: float
    entry_price: float
    exit_price: float
    entry_date: datetime
    exit_date: datetime
    realized_pnl: float
    return_pct: float
    holding_days: int


class ClosedPositionListResponse(BaseModel):
    """A list of closed positions plus the matching total."""

    items: list[ClosedPositionRead]
    total: int


class SessionValueSnapshotRead(BaseModel):
    """An end-of-day portfolio-value snapshot for a session."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    snapshot_date: date
    total_value: float
    cash_value: float
    positions_value: float
    daily_pnl: float
    daily_pnl_pct: float
    positions: list[dict[str, Any]]
    created_at: datetime
    # Rebased buy-and-hold value of the session's benchmark as of this snapshot's
    # date (allocated capital in the benchmark, rebased to the session start), or
    # ``None`` when the benchmark has no stored price on or before that date.
    benchmark_value: float | None = None


class SessionValueHistoryResponse(BaseModel):
    """A session's value snapshots (oldest first) plus the matching total."""

    items: list[SessionValueSnapshotRead]
    total: int


class PaperTradingSessionKpisRead(BaseModel):
    """A session's live performance KPIs.

    ``current_value`` is the live net asset value (net of fees); ``realised_pnl``
    the cumulative gross realised P&L; ``unrealised_pnl`` the live mark-to-market on
    open positions; ``total_fees`` the cumulative per-trade transaction cost;
    ``total_return`` the absolute gain/loss versus allocated capital and
    ``total_return_pct`` the same as a fraction; ``sharpe_ratio`` is ``None`` until
    the session has accumulated enough daily history. ``benchmark`` is the session's
    benchmark id; ``benchmark_return_pct`` the benchmark's fractional return over the
    session's period and ``excess_return_pct`` the session's return minus it, both
    ``None`` when the benchmark has insufficient stored prices.
    """

    current_value: float
    realised_pnl: float
    unrealised_pnl: float
    total_fees: float
    total_return: float
    total_return_pct: float
    sharpe_ratio: float | None
    benchmark: str
    benchmark_return_pct: float | None
    excess_return_pct: float | None


class AIDailySnapshotResponse(BaseModel):
    """Result of the daily snapshot fan-out: how many sessions were snapshotted."""

    sessions_snapshotted: int
    session_ids: list[uuid.UUID] = Field(default_factory=list)


class BenchmarkCatalogEntry(BaseModel):
    """One selectable benchmark index: its stable id and display name."""

    id: str
    name: str


class AIBenchmarkIngestResponse(BaseModel):
    """Result of the benchmark price-ingestion cron: rows upserted per benchmark.

    ``benchmarks_ingested`` counts benchmarks that stored at least one row (a
    benchmark whose fetch failed contributes 0 and is not counted);
    ``prices_upserted`` is the total rows upserted across all benchmarks; ``counts``
    breaks the total down by benchmark id.
    """

    benchmarks_ingested: int
    prices_upserted: int
    counts: dict[str, int]


class SessionBenchmarkChangeRequest(BaseModel):
    """Request body for changing a session's benchmark."""

    benchmark: str = Field(..., description="A benchmark id from the catalog")


# --------------------------------------------------------------------------- #
# AI-managed portfolio
# --------------------------------------------------------------------------- #


class AIPortfolioBuildRequest(BaseModel):
    """Request body for building an AI-managed portfolio.

    The build allocates over the entire current asset universe (with bounded
    discovery of new assets), so no candidate ticker list or per-asset/position
    caps are accepted.
    """

    allocated_capital: float = Field(default=10000.0, ge=1000)
    risk_profile: str = Field(default="balanced")
    asset_types: str = Field(
        default=AssetScope.BOTH.value,
        description="Which asset categories the portfolio may hold: "
        "'stocks', 'crypto', or 'both' (default).",
    )
    daily_rebalancing: bool = Field(
        default=False,
        description="Enroll this session in automatic daily rebalancing.",
    )
    benchmark: Benchmark | None = Field(
        default=None,
        description="Benchmark index to compare the session against (a catalog "
        "id). Defaults to the configured default benchmark (S&P 500).",
    )

    @field_validator("asset_types")
    @classmethod
    def _validate_asset_types(cls, value: str) -> str:
        """Reject anything that is not a known :class:`AssetScope` (→ 422)."""
        try:
            return AssetScope(value).value
        except ValueError as exc:
            allowed = ", ".join(scope.value for scope in AssetScope)
            raise ValueError(f"asset_types must be one of: {allowed}") from exc


class AIPortfolioBuildResponse(BaseModel):
    """Accepted response for a queued build."""

    event_id: uuid.UUID
    status: str


class AIRebalanceResponse(BaseModel):
    """Accepted response for a queued (or already-running) rebalance."""

    event_id: uuid.UUID
    status: str
    started: bool


class AIDailyRebalanceResponse(BaseModel):
    """Result of the daily fan-out: which sessions were triggered vs skipped."""

    sessions_triggered: int
    session_ids: list[uuid.UUID] = Field(default_factory=list)
    skipped_already_running: list[uuid.UUID] = Field(default_factory=list)


class AIPortfolioEventRead(BaseModel):
    """An AI portfolio event: request, status, agent output, and trade actions."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID | None
    portfolio_id: uuid.UUID | None
    event_type: str
    status: str
    request_payload: dict[str, Any] | None
    result_payload: dict[str, Any] | None
    actions_taken: list[dict[str, Any]] | None
    research: list[dict[str, Any]] | None
    error: str | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


class AIPortfolioRunListResponse(BaseModel):
    """A page of AI runs (build + rebalance events) plus the matching total."""

    items: list[AIPortfolioEventRead]
    total: int


class AIPortfolioRunDetail(BaseModel):
    """One AI run with the trades it opened and the positions it closed.

    The event carries the run's reasoning (``result_payload``) and research
    transcript; ``trades``/``closed_positions`` are the orders it produced.
    """

    event: AIPortfolioEventRead
    trades: list[PaperTradeRead]
    closed_positions: list[ClosedPositionRead]
    # The rebalance-prompt version frozen onto the run's session, when it has one.
    # Null for an event with no session (e.g. a build that failed before creating it).
    rebalance_prompt_version: int | None = None


# --------------------------------------------------------------------------- #
# Dashboard                                                                    #
# --------------------------------------------------------------------------- #


class DashboardBreakdownEntry(BaseModel):
    """One group of a composition breakdown: a display key and its asset count.

    ``key`` is the group value as a display string. Assets with no sector are
    surfaced under the explicit sentinel key "no sector" rather than dropped.
    """

    model_config = ConfigDict(from_attributes=True)

    key: str
    count: int


class AssetUniverseMetrics(BaseModel):
    """Asset-universe size and composition.

    ``by_category``/``by_sector`` are ordered by descending count then key;
    ``by_sector`` reports only sectors that have assets (empty on an empty
    universe). ``eligible + ineligible == total``.
    """

    model_config = ConfigDict(from_attributes=True)

    total: int
    eligible: int
    ineligible: int
    by_category: list[DashboardBreakdownEntry]
    by_sector: list[DashboardBreakdownEntry]


class PaperTradingMetrics(BaseModel):
    """Paper-trading activity: active sessions and recently executed trades."""

    model_config = ConfigDict(from_attributes=True)

    active_sessions: int
    recent_trades: int


class DashboardMetrics(BaseModel):
    """The full dashboard overview payload returned by the endpoint."""

    model_config = ConfigDict(from_attributes=True)

    assets: AssetUniverseMetrics
    portfolio_count: int
    paper_trading: PaperTradingMetrics
