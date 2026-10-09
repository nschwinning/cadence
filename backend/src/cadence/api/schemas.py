"""Pydantic v2 response/request schemas for the API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cadence.assets.category import AssetScope
from cadence.config import settings
from cadence.dashboard.constants import DashboardRange
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


class AssetUniverseEvaluationRead(BaseModel):
    """The AI evaluation of the whole asset universe, with an outdated flag.

    ``outdated`` is computed on read against the current universe fingerprint, so
    it is not an attribute of the stored row and is set explicitly by the router.
    """

    model_config = ConfigDict(from_attributes=True)

    narrative: str
    strengths: list[str]
    concerns: list[str]
    suggestions: list[str]
    generated_at: datetime
    outdated: bool


class AssetUniverseEvaluationResponse(BaseModel):
    """Envelope for the universe evaluation; ``evaluation`` is null when none.

    ``evaluation`` is ``None`` when the universe is empty (nothing to assess yet);
    otherwise it carries the current evaluation and its outdated flag.
    """

    evaluation: AssetUniverseEvaluationRead | None = None


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
    # Total capital contributed to the session (original build capital plus every
    # later increase). Equal to ``allocated_capital`` — surfaced under an explicit
    # name so the UI can label the Capital tile as total contributed capital.
    contributed_capital: float = 0.0
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
    # The crypto-rebalance-prompt version frozen at build time (weekend crypto-only run).
    crypto_rebalance_prompt_version: int
    # The benchmark index this session is compared against (a catalog id).
    benchmark: str
    # Which asset categories this session may hold: 'stocks', 'crypto', or 'both'.
    # Lives in ``session_metadata["asset_types"]`` (not an ORM column), so it is
    # populated by ``_populate_asset_types`` below; legacy sessions default to 'both'.
    asset_types: str = AssetScope.BOTH.value
    # Whether the session opted into the technical-indicator trend strategy
    # (frozen at build time). False for sessions built before this option existed.
    use_technical_indicators: bool
    # Whether the session opted into the automatic hard stop-loss (frozen at build
    # time). False for sessions built before this option existed.
    stop_loss_enabled: bool
    # The per-session stop-loss threshold (fraction, e.g. 0.15 = 15%) frozen at
    # build time; null when the stop-loss is disabled.
    stop_loss_pct: float | None
    # Whether the session opted into the deterministic risk guardrails (frozen at
    # build time). False for sessions built before this option existed.
    risk_guardrails_enabled: bool
    # The frozen guardrail parameters (fractions, e.g. 0.25 = 25%), null when the
    # guardrails are disabled. The per-asset cap reuses ``max_allocation_pct``
    # above (1.0 = no cap when guardrails off).
    max_asset_class_pct: float | None
    min_positions: int | None
    max_invested_pct: float | None

    @model_validator(mode="after")
    def _populate_asset_types(self) -> PaperTradingSessionRead:
        """Source ``asset_types`` from ``session_metadata`` (not an ORM column).

        ``from_attributes`` cannot auto-fill it because the value lives in the JSON
        metadata dict. Legacy sessions with no recorded scope read as ``both``; an
        unrecognized stored value also falls back to ``both`` rather than erroring.
        """
        scope = (self.session_metadata or {}).get(
            "asset_types", AssetScope.BOTH.value
        )
        try:
            self.asset_types = AssetScope(scope).value
        except ValueError:
            self.asset_types = AssetScope.BOTH.value
        # ``allocated_capital`` is the running total of contributed capital; surface
        # it under the explicit ``contributed_capital`` name for the UI.
        self.contributed_capital = self.allocated_capital
        return self


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
    # The AI build/rebalance event that produced this run, when applicable
    # (null for stop-loss and scheduled/manual runs).
    ai_portfolio_event_id: uuid.UUID | None
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


class SessionValueComparisonPoint(BaseModel):
    """A single (date, total value) point of a session's value history."""

    model_config = ConfigDict(from_attributes=True)

    snapshot_date: date
    total_value: float


class SessionValueComparisonSeries(BaseModel):
    """One session's value series for the multi-session comparison chart.

    ``label`` is the session's portfolio name, falling back to its strategy key.
    ``points`` is ordered oldest date first and is empty when the session has no
    snapshots yet. Return percentage is derived by the client from ``total_value``
    and ``allocated_capital``.
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    label: str
    allocated_capital: float
    points: list[SessionValueComparisonPoint]


class SessionValueComparisonResponse(BaseModel):
    """Every non-archived session's value series, for the comparison chart."""

    sessions: list[SessionValueComparisonSeries]


class SessionGroupPerformance(BaseModel):
    """Performance attribution for one sector/category group within a session.

    ``key`` is the sector or category name (or the "No sector"/"Unknown" sentinel
    bucket). ``realized_pnl`` is the group's cumulative closed-position P&L,
    ``unrealized_pnl`` the live mark-to-market on its open positions, ``total_pnl``
    their sum, and ``market_value`` the group's open-position market value.
    ``return_pct`` is ``total_pnl`` over the group's invested cost basis, or ``None``
    when that basis is zero (unavailable rather than divide-by-zero).
    """

    model_config = ConfigDict(from_attributes=True)

    key: str
    market_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    return_pct: float | None


class SessionSectorPerformanceRead(BaseModel):
    """A session's P&L attributed to sectors and to categories."""

    by_sector: list[SessionGroupPerformance]
    by_category: list[SessionGroupPerformance]


class PaperTradingSessionKpisRead(BaseModel):
    """A session's live performance KPIs.

    ``current_value`` is the live net asset value (net of fees);
    ``unallocated_cash`` the portion of that value currently held as cash (live value
    minus marked-to-market positions value); ``realised_pnl``
    the cumulative gross realised P&L; ``unrealised_pnl`` the live mark-to-market on
    open positions; ``total_fees`` the cumulative transaction cost;
    ``daily_avg_orders`` the number of recorded orders (trades) divided by the
    number of recorded daily value snapshots (``None`` until the session has a
    snapshot);
    ``total_return`` the absolute gain/loss versus allocated capital and
    ``total_return_pct`` the same as a fraction; ``sharpe_ratio`` is ``None`` until
    the session has accumulated enough daily history. ``benchmark`` is the session's
    benchmark id; ``benchmark_return_pct`` the benchmark's fractional return over the
    session's period and ``excess_return_pct`` the session's return minus it;
    ``excess_return`` is that excess in absolute terms (net-of-fees dollar gain minus
    the benchmark's dollar gain on the same capital). All three are ``None`` when the
    benchmark has insufficient stored prices.

    ``max_drawdown`` is the largest peak-to-trough decline of the daily NAV series as
    a non-negative fraction (``None`` without snapshots). ``win_rate`` is the fraction
    of closed positions with realised P&L > 0; ``average_win``/``average_loss`` the
    mean realised P&L of winning/losing closed positions; ``best_trade``/``worst_trade``
    the max/min realised P&L. The trade figures are ``None`` with no closed positions,
    and a win/loss average is ``None`` when that side has no members.
    """

    current_value: float
    unallocated_cash: float
    realised_pnl: float
    unrealised_pnl: float
    total_fees: float
    daily_avg_orders: float | None
    total_return: float
    total_return_pct: float
    sharpe_ratio: float | None
    benchmark: str
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    excess_return: float | None
    max_drawdown: float | None
    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    best_trade: float | None
    worst_trade: float | None


class AIDailySnapshotResponse(BaseModel):
    """Result of the daily snapshot fan-out: how many sessions were snapshotted."""

    sessions_snapshotted: int
    session_ids: list[uuid.UUID] = Field(default_factory=list)


class AIDailyRunSnapshotResponse(BaseModel):
    """Result of the daily-run learning-snapshot assembly: how many were recorded.

    The consolidated learning rows themselves are backend-only and never returned —
    only the count and the affected session ids are surfaced to the cron caller.
    """

    snapshots_recorded: int
    session_ids: list[uuid.UUID] = Field(default_factory=list)


class AIStopLossScanResponse(BaseModel):
    """Result of a stop-loss scan: how many positions were stopped out."""

    positions_stopped: int
    session_ids: list[uuid.UUID] = Field(default_factory=list)


class TechnicalIndicatorRunResponse(BaseModel):
    """Result of triggering the technical-indicator precompute cron.

    ``started`` is ``False`` when a run was already in flight (the existing run's
    id is returned instead of a new one), so the trigger is safe to call twice.
    """

    run_id: int
    status: str
    started: bool


class IndicatorParamRead(BaseModel):
    """One period/lookback parameter defining an indicator."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    value: int | float


class IndicatorInfoRead(BaseModel):
    """A single indicator in the computed set with its defining parameters."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    params: list[IndicatorParamRead]


class GateConditionRead(BaseModel):
    """One condition of the trend gate; ``threshold`` is null for comparisons
    between two indicators (e.g. SMA50 > SMA200)."""

    model_config = ConfigDict(from_attributes=True)

    description: str
    threshold: float | None = None


class TrendGateConfigRead(BaseModel):
    """The deterministic uptrend gate: regime + momentum conditions, the soft OBV
    bonus, and the missing-indicator rule."""

    model_config = ConfigDict(from_attributes=True)

    description: str
    regime: list[GateConditionRead]
    momentum: list[GateConditionRead]
    obv_bonus: str
    missing_indicator_rule: str


class ReversalFlagInfoRead(BaseModel):
    """One reversal flag and what sets it."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    description: str


class ReversalFlagsConfigRead(BaseModel):
    """The reversal-flag definitions plus their tunable thresholds."""

    model_config = ConfigDict(from_attributes=True)

    flags: list[ReversalFlagInfoRead]
    rsi_overbought: float
    slope_flatten_eps: float


class TechnicalIndicatorConfig(BaseModel):
    """The read-only technical-indicator configuration: the indicator set, the
    trend-gate rules + thresholds, and the reversal-flag definitions."""

    model_config = ConfigDict(from_attributes=True)

    indicators: list[IndicatorInfoRead]
    trend_gate: TrendGateConfigRead
    reversal_flags: ReversalFlagsConfigRead


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


class SessionCapitalIncreaseRequest(BaseModel):
    """Request body for increasing a session's capital (increase-only)."""

    amount: float = Field(
        ...,
        gt=0,
        description="Positive amount of capital to add to the session.",
    )


class SessionScopeChangeRequest(BaseModel):
    """Request body for changing a session's asset scope."""

    asset_types: str = Field(
        ...,
        description="Which asset categories the session may hold: "
        "'stocks', 'crypto', or 'both'.",
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
    use_technical_indicators: bool = Field(
        default=False,
        description="Opt this portfolio into the technical-indicator trend "
        "strategy (frozen at build time). When enabled, both the build and daily "
        "rebalances hard-filter candidates through the trend gate and attach "
        "holdings reversal context. Defaults to off (opt-in).",
    )
    stop_loss_enabled: bool = Field(
        default=False,
        description="Opt this portfolio into the automatic hard stop-loss (frozen "
        "at build time). When enabled, a held position is fully exited once its live "
        "price falls to or below avg_cost × (1 − stop_loss_pct). Defaults to off "
        "(opt-in).",
    )
    stop_loss_pct: float | None = Field(
        default=None,
        gt=0,
        lt=1,
        description="Stop-loss threshold as a fraction of weighted-average cost "
        "(e.g. 0.15 = a 15% drop triggers a whole-position exit). Applies only when "
        "stop_loss_enabled is true; defaults to the configured default threshold "
        "when the stop-loss is enabled without an explicit value.",
    )
    risk_guardrails_enabled: bool = Field(
        default=False,
        description="Opt this portfolio into the deterministic risk guardrails "
        "(frozen at build time). When enabled, both the build and daily rebalances "
        "clamp/redistribute/scale the AI's target weights to the caps below. "
        "Defaults to off (opt-in).",
    )
    max_allocation_pct: float | None = Field(
        default=None,
        gt=0,
        le=1,
        description="Maximum fraction of the portfolio any single asset may hold. "
        "Applies only when risk_guardrails_enabled is true; defaults to the "
        "configured default when the guardrails are enabled without an explicit "
        "value.",
    )
    max_asset_class_pct: float | None = Field(
        default=None,
        gt=0,
        le=1,
        description="Maximum fraction of the portfolio any single asset class may "
        "hold. Applies only when risk_guardrails_enabled is true; defaults to the "
        "configured default when enabled without an explicit value.",
    )
    min_positions: int | None = Field(
        default=None,
        ge=1,
        description="Minimum number of positions the AI is asked to hold (a "
        "diversification floor; surfaced rather than fabricated when the AI returns "
        "fewer). Applies only when risk_guardrails_enabled is true; defaults to the "
        "configured default when enabled without an explicit value.",
    )
    max_invested_pct: float | None = Field(
        default=None,
        gt=0,
        le=1,
        description="Maximum fraction of the allocated capital that may be invested "
        "(the remainder is held as a cash buffer). Applies only when "
        "risk_guardrails_enabled is true; defaults to the configured default when "
        "enabled without an explicit value.",
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

    @model_validator(mode="after")
    def _default_stop_loss_pct(self) -> AIPortfolioBuildRequest:
        """Fill the stop-loss threshold from the configured default when enabled.

        When the build opts into the stop-loss without an explicit threshold, the
        global ``STOP_LOSS_DEFAULT_PCT`` applies. When the stop-loss is off, any
        supplied threshold is dropped so a disabled session never carries one.
        """
        if self.stop_loss_enabled:
            if self.stop_loss_pct is None:
                self.stop_loss_pct = settings.STOP_LOSS_DEFAULT_PCT
        else:
            self.stop_loss_pct = None
        return self

    @model_validator(mode="after")
    def _default_guardrails(self) -> AIPortfolioBuildRequest:
        """Fill guardrail parameters from configured defaults when enabled.

        When the build opts into the guardrails without explicit parameters, the
        global ``GUARDRAIL_DEFAULT_*`` values apply. When the guardrails are off,
        any supplied parameters are dropped so a disabled session never carries them.
        """
        if self.risk_guardrails_enabled:
            if self.max_allocation_pct is None:
                self.max_allocation_pct = settings.GUARDRAIL_DEFAULT_MAX_ASSET_PCT
            if self.max_asset_class_pct is None:
                self.max_asset_class_pct = (
                    settings.GUARDRAIL_DEFAULT_MAX_ASSET_CLASS_PCT
                )
            if self.min_positions is None:
                self.min_positions = settings.GUARDRAIL_DEFAULT_MIN_POSITIONS
            if self.max_invested_pct is None:
                self.max_invested_pct = settings.GUARDRAIL_DEFAULT_MAX_INVESTED_PCT
        else:
            self.max_allocation_pct = None
            self.max_asset_class_pct = None
            self.min_positions = None
            self.max_invested_pct = None
        return self


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
    #: Freshly-built sessions deferred because their build orders have not yet
    #: filled; picked up by a later trigger once they settle.
    skipped_awaiting_build_fill: list[uuid.UUID] = Field(default_factory=list)


class AIDailyCryptoRebalanceResponse(AIDailyRebalanceResponse):
    """Result of the weekend crypto-only fan-out.

    Mirrors :class:`AIDailyRebalanceResponse` and adds the crypto-specific skip
    bucket: sessions whose configured asset scope does not include crypto are
    skipped before a job is started, so they never create an AI event.
    """

    #: Sessions skipped before starting a job because their configured asset scope
    #: does not include crypto (stocks-only), regardless of current holdings.
    skipped_not_crypto_scope: list[uuid.UUID] = Field(default_factory=list)


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
    # Per-run trend-decision context (dropped candidates + indicator annotations
    # handed to the AI); null for runs that performed no gating.
    trend_context: dict[str, Any] | None
    error: str | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


class AIPortfolioRunListResponse(BaseModel):
    """A page of AI runs (build + rebalance events) plus the matching total."""

    items: list[AIPortfolioEventRead]
    total: int


class AIPortfolioEventListResponse(BaseModel):
    """A page of a session's AI-portfolio events plus the matching total."""

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


# --------------------------------------------------------------------------- #
# Dashboard overview (range-scoped)                                            #
# --------------------------------------------------------------------------- #


class DashboardSessionValuePoint(BaseModel):
    """One (date, value) point of a session's range-windowed value series."""

    model_config = ConfigDict(from_attributes=True)

    date: date
    value: float


class DashboardSessionPerformance(BaseModel):
    """A single active session's range-scoped performance data.

    ``pnl``/``fees`` are relative to the selected range; ``points`` is the value
    series windowed to the range (oldest first) for the client to sum and
    re-aggregate on selection changes without re-fetching.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    allocated_capital: float
    current_value: float
    pnl: float
    fees: float
    points: list[DashboardSessionValuePoint]


class DashboardAutomationRun(BaseModel):
    """A reference to a single AI run for the automation summary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    status: str
    created_at: datetime
    session_id: uuid.UUID | None = None


class DashboardAutomationSummary(BaseModel):
    """Health of the AI rebalance automation, scoped to the selected range."""

    model_config = ConfigDict(from_attributes=True)

    latest_run: DashboardAutomationRun | None = None
    in_flight: bool
    failed_in_range: int
    next_run_approx: datetime
    next_run_is_approximate: bool


class DashboardActivityEntry(BaseModel):
    """One AI run in the recent-activity feed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID | None = None
    session_label: str | None = None
    kind: str
    status: str
    created_at: datetime


class DashboardUniverseBalance(BaseModel):
    """Current composition of the asset universe (range-independent)."""

    model_config = ConfigDict(from_attributes=True)

    total: int
    eligible: int
    ineligible: int
    sectors_count: int
    top_sector_key: str | None = None
    top_sector_share: float
    top_category_key: str | None = None
    top_category_share: float


class DashboardPerformerEntry(BaseModel):
    """One asset's market return over the range, for the performer rankings."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: int
    ticker: str
    name: str | None = None
    return_pct: float


class DashboardUniversePerformers(BaseModel):
    """Best and worst tracked assets by market return over the range."""

    model_config = ConfigDict(from_attributes=True)

    best: list[DashboardPerformerEntry]
    worst: list[DashboardPerformerEntry]


class DashboardOverview(BaseModel):
    """The full range-scoped dashboard overview payload."""

    model_config = ConfigDict(from_attributes=True)

    range: DashboardRange
    sessions: list[DashboardSessionPerformance]
    automation: DashboardAutomationSummary
    recent_activity: list[DashboardActivityEntry]
    universe_balance: DashboardUniverseBalance
    universe_performers: DashboardUniversePerformers


# --- System status -----------------------------------------------------------


class BackendStatusRead(BaseModel):
    """Live-probe status of a single external backend.

    Carries only booleans and non-secret identifiers — never a key, secret, or
    token value. ``reachable`` is ``None`` when no probe was performed (the
    backend is unconfigured, or the broker is in offline/stub mode); ``True`` or
    ``False`` reflect the live probe result.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    configured: bool
    identifier: str | None = None
    reachable: bool | None = None
    latency_ms: float | None = None
    detail: str | None = None


class SystemStatusRead(BaseModel):
    """Aggregated live status of every external backend the app depends on."""

    model_config = ConfigDict(from_attributes=True)

    backends: list[BackendStatusRead]
