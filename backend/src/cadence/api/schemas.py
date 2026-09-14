"""Pydantic v2 response/request schemas for the API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
    category: str
    sector: str | None
    exchange: str | None
    currency: str
    market_cap_eur: float | None
    avg_daily_turnover_eur: float | None
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


class PaperTradingSessionListResponse(BaseModel):
    """A list of paper-trading sessions plus the matching total."""

    items: list[PaperTradingSessionRead]
    total: int


class PaperTradeRead(BaseModel):
    """A single recorded paper trade (fill)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
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


# --------------------------------------------------------------------------- #
# AI-managed portfolio
# --------------------------------------------------------------------------- #


class AIPortfolioBuildRequest(BaseModel):
    """Request body for building an AI-managed portfolio."""

    tickers: list[str] = Field(
        ..., min_length=2, description="Candidate stock tickers (at least two)"
    )
    allocated_capital: float = Field(default=100000.0, ge=1000)
    risk_profile: str = Field(default="balanced")
    allow_new_picks: bool = Field(default=False)
    allow_short: bool = Field(default=False)
    max_stock_count: int = Field(default=8, ge=2, le=10)
    daily_rebalancing: bool = Field(
        default=False,
        description="Enroll this session in automatic daily rebalancing.",
    )


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
    error: str | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


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
