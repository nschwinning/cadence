// Types mirroring the backend API contract. Keep in sync with the FastAPI
// pydantic schemas (see backend `cadence/api/schemas.py`).

export type HealthStatus = 'ok' | 'degraded';
export type DatabaseStatus = 'connected' | 'disconnected';

/**
 * Response shape of `GET /health`. This endpoint always returns HTTP 200;
 * `status` reflects overall health and `database` reflects DB connectivity.
 */
export interface HealthResponse {
  status: HealthStatus;
  database: DatabaseStatus;
}

// --------------------------------------------------------------------------- //
// Assets
// --------------------------------------------------------------------------- //

/** The individual eligibility criteria evaluated per asset. */
export type CriterionName =
  | 'price'
  | 'avg_daily_turnover'
  | 'market_cap'
  | 'history';

/**
 * Result of evaluating a single eligibility criterion against an asset's
 * (EUR-normalized) metric. `value` is the evaluated metric (null when it could
 * not be resolved); `threshold` is the constant it was compared against.
 */
export interface CriterionResult {
  name: CriterionName;
  passed: boolean;
  value: number | null;
  threshold: number;
}

/**
 * The instrument category an asset is classified into, derived from the
 * market-data provider's instrument type. Unknown types fall back to `other`.
 */
export type AssetCategory = 'stock' | 'crypto' | 'etf' | 'fund' | 'other';

/**
 * The economic sector an asset belongs to, from the market-data provider's
 * bounded taxonomy (stored as the provider's stable slug). `null` when the
 * provider reports no sector. Mirrors the backend `Sector` enum values.
 */
export type Sector =
  | 'technology'
  | 'financial-services'
  | 'healthcare'
  | 'consumer-cyclical'
  | 'consumer-defensive'
  | 'industrials'
  | 'energy'
  | 'basic-materials'
  | 'real-estate'
  | 'utilities'
  | 'communication-services';

/** Columns the assets list can be sorted by. Mirrors the backend `SORT_FIELDS`. */
export type AssetSortField = 'ticker' | 'name';

/** Sort direction for the assets list. Mirrors the backend `SORT_DIRECTIONS`. */
export type AssetSortDirection = 'asc' | 'desc';

/**
 * A stored asset with its EUR-normalized metric snapshot and eligibility
 * result. Mirrors the backend `AssetRead` schema for `/api/v1/assets`.
 */
export interface Asset {
  id: number;
  ticker: string;
  name: string | null;
  category: AssetCategory;
  sector: Sector | null;
  exchange: string | null;
  currency: string;
  market_cap_eur: number | null;
  avg_daily_turnover_eur: number | null;
  history_years: number | null;
  is_eligible: boolean;
  criteria_results: CriterionResult[];
  created_at: string;
}

/**
 * A page of stored assets. Mirrors the backend `AssetListResponse` envelope for
 * `GET /api/v1/assets`: `items` is the current bounded page (in the requested
 * sort order, default ticker ascending) and `total` is the count of all assets
 * matching the active search and filters.
 */
export interface AssetPage {
  items: Asset[];
  total: number;
}

/** Request body for `POST /api/v1/assets`. */
export interface AssetCreate {
  ticker: string;
}

/**
 * A single daily closing price in an asset's price-history series. `date` is an
 * ISO `YYYY-MM-DD` calendar day; `close` is the closing price in the asset's
 * native trading currency.
 */
export interface AssetDetailHistoryPoint {
  date: string;
  close: number;
}

/**
 * A single asset's detail snapshot. Mirrors the backend `AssetDetailRead`
 * schema for `GET /api/v1/assets/{ticker}/details`. All monetary values are in
 * the asset's native trading `currency` — NOT EUR.
 */
export interface AssetDetail {
  ticker: string;
  name: string | null;
  category: AssetCategory;
  sector: Sector | null;
  exchange: string | null;
  currency: string;
  current_price: number | null;
  previous_close: number | null;
  short_description: string | null;
  country: string | null;
  city: string | null;
  employees: number | null;
  website: string | null;
  volume: number | null;
  avg_volume: number | null;
  price_history: AssetDetailHistoryPoint[];
  snapshot_date: string;
}

// --------------------------------------------------------------------------- //
// Recommendations
// --------------------------------------------------------------------------- //

/**
 * Lifecycle phase of a recommendation run. `queued`, `searching`, and
 * `validating` are non-terminal; `completed` and `failed` are terminal — no
 * further status changes occur, so pollers stop.
 */
export type RunPhase =
  | 'queued'
  | 'searching'
  | 'validating'
  | 'completed'
  | 'failed';

/**
 * The disposition of a single candidate ticker the run evaluated. Mirrors the
 * backend `CandidateOutcome` enum values.
 */
export type CandidateOutcome =
  | 'added'
  | 'skipped-duplicate'
  | 'skipped-ineligible'
  | 'error';

/**
 * One candidate ticker produced by a recommendation run, with its outcome and an
 * optional human-readable `detail`.
 */
export interface RecommendationCandidateResult {
  ticker: string;
  outcome: CandidateOutcome;
  detail: string | null;
}

/**
 * A recommendation run: an async job that searches for and validates candidate
 * assets. Mirrors the backend `RecommendationRunRead` schema. `results` fills in
 * as the run progresses and is final once `status` is terminal.
 */
export interface RecommendationRun {
  id: number;
  created_at: string;
  status: RunPhase;
  requested_count: number;
  requested_categories: string[];
  prompt: string | null;
  tool_call_count: number;
  results: RecommendationCandidateResult[];
  error: string | null;
}

/**
 * Request body for `POST /api/v1/recommendations`. `count` is the number of
 * assets to find (integer >= 1); `categories` limits the search (>= 1 entry).
 * Responds 202 with the created `RecommendationRun` or 422 on validation failure.
 */
export interface RecommendationRunCreate {
  count: number;
  categories: AssetCategory[];
}

// --------------------------------------------------------------------------- //
// Portfolios
// --------------------------------------------------------------------------- //

/** How a portfolio came to exist. Mirrors the backend `PortfolioSource` enum. */
export type PortfolioSource =
  | 'recommended'
  | 'manual'
  | 'legacy_backtest'
  | 'legacy_cycle'
  | 'ai_managed';

/** Coarse risk appetite. Mirrors the backend `RiskProfile` enum. */
export type RiskProfile = 'conservative' | 'balanced' | 'aggressive';

/** A stored portfolio. Mirrors the backend `PortfolioRead` schema. */
export interface Portfolio {
  id: string;
  name: string;
  description: string | null;
  stocks: string[];
  max_allocation_pct: number;
  source: string;
  risk_profile: string | null;
  source_run_id: string | null;
  created_at: string;
}

/** A list of stored portfolios plus the matching total. */
export interface PortfolioListResponse {
  items: Portfolio[];
  total: number;
}

/** Request body for `POST /api/v1/portfolios`. */
export interface PortfolioCreate {
  name: string;
  stocks: string[];
  source?: PortfolioSource;
  description?: string | null;
  risk_profile?: RiskProfile | null;
  max_allocation_pct?: number;
  source_run_id?: string | null;
}

// --------------------------------------------------------------------------- //
// Paper trading (read-only)
// --------------------------------------------------------------------------- //

/** Lifecycle status of a paper-trading session. */
export type SessionStatus = 'active' | 'paused' | 'stopped';

/** How a paper-trading session is run automatically. */
export type ScheduleMode = 'MANUAL' | 'SCHEDULED' | 'DAILY_REBALANCING';

/** A paper-trading session and its running totals. Mirrors `PaperTradingSessionRead`. */
export interface PaperTradingSession {
  id: string;
  portfolio_id: string;
  strategy_key: string;
  status: string;
  allocated_capital: number;
  max_allocation_pct: number;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  total_trades: number;
  total_pnl: number;
  session_metadata: Record<string, unknown> | null;
  schedule_mode: string;
}

/** A list of paper-trading sessions plus the matching total. */
export interface PaperTradingSessionListResponse {
  items: PaperTradingSession[];
  total: number;
}

/** A single recorded paper trade (fill). Mirrors `PaperTradeRead`. */
export interface PaperTrade {
  id: string;
  session_id: string;
  ticker: string;
  side: string;
  quantity: number;
  price: number;
  notional: number;
  signal_type: string;
  executed_at: string;
  order_id: string | null;
  order_status: string;
  filled_price: number | null;
  filled_at: string | null;
}

/** A list of paper trades plus the matching total. */
export interface PaperTradeListResponse {
  items: PaperTrade[];
  total: number;
}

/** A record of a single session run. Mirrors `SessionRunRead`. */
export interface SessionRun {
  id: string;
  session_id: string;
  run_at: string;
  signals_scanned: number;
  signals_actionable: number;
  orders_executed: number;
  orders_skipped: number;
  details: Record<string, unknown>[] | null;
  status: string;
  run_trigger: string;
  duration_ms: number | null;
}

/** A list of session runs plus the matching total. */
export interface SessionRunListResponse {
  items: SessionRun[];
  total: number;
}

/** A closed position with realized P&L. Mirrors `ClosedPositionRead`. */
export interface ClosedPosition {
  id: string;
  session_id: string;
  ticker: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  entry_date: string;
  exit_date: string;
  realized_pnl: number;
  return_pct: number;
  holding_days: number;
}

/** A list of closed positions plus the matching total. */
export interface ClosedPositionListResponse {
  items: ClosedPosition[];
  total: number;
}

// --------------------------------------------------------------------------- //
// AI-managed portfolio
// --------------------------------------------------------------------------- //

/** Which AI job an event records. Mirrors the backend `EventType` enum. */
export type AIEventType = 'build' | 'rebalance';

/**
 * Lifecycle status of an AI portfolio event. `queued`/`running` are non-terminal;
 * `succeeded`/`partial`/`failed`/`skipped` are terminal, so pollers stop.
 */
export type AIEventStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'partial'
  | 'failed'
  | 'skipped';

/**
 * Request body for `POST /api/v1/ai-portfolio/build`. Every build allocates
 * across the app's ENTIRE asset universe automatically — the AI decides each
 * asset's weight (long-only, no caps) and may research and add new assets — so
 * callers no longer supply tickers or a position count. Backend defaults:
 * `allocated_capital` 100000, `risk_profile` "balanced", `daily_rebalancing`
 * false.
 */
export interface AIPortfolioBuildRequest {
  allocated_capital?: number;
  risk_profile?: string;
  daily_rebalancing?: boolean;
}

/**
 * One AI-chosen target weight in a rebalance result. `allocation_pct` is the
 * target share of capital (long-only); `confidence` is the AI's conviction.
 */
export interface AITargetAllocation {
  ticker: string;
  company_name: string;
  allocation_pct: number;
  investment_thesis: string;
  confidence: number;
}

/**
 * The `result_payload` of a rebalance event: the AI's narrative evaluation, the
 * new target allocations to re-weight toward, and an overall health assessment.
 */
export interface AIRebalanceResultPayload {
  evaluation_summary: string;
  target_allocations: AITargetAllocation[];
  portfolio_health: string;
}

/** Accepted (202) response for a queued build. */
export interface AIPortfolioBuildResponse {
  event_id: string;
  status: string;
}

/** Accepted response for a queued (or already-running) rebalance. */
export interface AIRebalanceResponse {
  event_id: string;
  status: string;
  started: boolean;
}

/** Result of the daily fan-out: which sessions were triggered vs skipped. */
export interface AIDailyRebalanceResponse {
  sessions_triggered: number;
  session_ids: string[];
  skipped_already_running: string[];
}

/**
 * An AI portfolio event: request, status, agent output, and trade actions.
 * Mirrors the backend `AIPortfolioEventRead` schema.
 */
export interface AIPortfolioEvent {
  id: string;
  session_id: string | null;
  portfolio_id: string | null;
  event_type: string;
  status: AIEventStatus;
  request_payload: Record<string, unknown> | null;
  result_payload: Record<string, unknown> | null;
  actions_taken: Record<string, unknown>[] | null;
  error: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
}

// --------------------------------------------------------------------------- //
// Dashboard
// --------------------------------------------------------------------------- //

/** One group of a composition breakdown: a display key and its asset count. */
export interface DashboardBreakdownEntry {
  key: string;
  count: number;
}

/** Asset-universe size and composition. Mirrors `AssetUniverseMetrics`. */
export interface AssetUniverseMetrics {
  total: number;
  eligible: number;
  ineligible: number;
  by_category: DashboardBreakdownEntry[];
  by_sector: DashboardBreakdownEntry[];
}

/** Paper-trading activity: active sessions and recently executed trades. */
export interface PaperTradingMetrics {
  active_sessions: number;
  recent_trades: number;
}

/** The full dashboard overview payload from `GET /api/v1/dashboard/metrics`. */
export interface DashboardMetrics {
  assets: AssetUniverseMetrics;
  portfolio_count: number;
  paper_trading: PaperTradingMetrics;
}
