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

/**
 * Which bucket an asset belongs to. `universe` assets are the tradable set used
 * for portfolio build/rebalance; `watchlist` assets are emerging candidates held
 * for research only. Mirrors the backend `AssetMembership` enum.
 */
export type AssetMembership = 'universe' | 'watchlist';

/**
 * Whether company fundamentals were successfully fetched. `available` — core
 * figures found; `partial` — a CIK resolved but only some figures; `unavailable`
 * — a fetch was attempted but EDGAR had no CIK/facts or was unreachable. Mirrors
 * the backend `FundamentalsStatus` values.
 */
export type FundamentalsStatus = 'available' | 'partial' | 'unavailable';

/**
 * One mapped annual figure from SEC EDGAR (e.g. revenue, net income, EPS), with
 * the reporting unit and the fiscal period it was taken from. Extra keys may be
 * present; the `document` is otherwise opaque.
 */
export interface FundamentalsFigure {
  value: number;
  unit?: string;
  fiscal_year?: number | null;
  period_end?: string | null;
  form?: string | null;
}

/**
 * Company fundamentals for an asset, as fetched from SEC EDGAR. Mirrors the
 * backend `AssetFundamentalsRead`. `document` is the raw mapped figures + company
 * details and is opaque to the API; `figures`/`company_details` are the known
 * top-level keys the watchlist view renders.
 */
export interface AssetFundamentals {
  source: string;
  status: FundamentalsStatus;
  cik: string | null;
  document: {
    figures?: Record<string, FundamentalsFigure>;
    company_details?: Record<string, unknown>;
    [key: string]: unknown;
  };
  fetched_at: string;
}

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
  /**
   * The brokerage's canonical symbol, captured at add time (e.g. `AAPL`,
   * `BTC/USD`). Null on legacy rows added before tradability verification.
   */
  alpaca_symbol: string | null;
  category: AssetCategory;
  sector: Sector | null;
  exchange: string | null;
  currency: string;
  /** The bucket the asset belongs to: the tradable `universe` or the `watchlist`. */
  membership: AssetMembership;
  market_cap_usd: number | null;
  avg_daily_turnover_usd: number | null;
  history_years: number | null;
  is_eligible: boolean;
  criteria_results: CriterionResult[];
  created_at: string;
  /**
   * Company fundamentals (SEC EDGAR), when fetched — populated for watchlist
   * assets. `null` for assets that have no fundamentals row.
   */
  fundamentals: AssetFundamentals | null;
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
 * The AI evaluation of the whole asset universe. Mirrors the backend
 * `AssetUniverseEvaluationRead`: a markdown `narrative` plus bulleted findings,
 * the `generated_at` time, and `outdated` (recomputed on read — true when the
 * universe has changed since the evaluation was generated).
 */
export interface AssetUniverseEvaluation {
  narrative: string;
  strengths: string[];
  concerns: string[];
  suggestions: string[];
  generated_at: string;
  outdated: boolean;
}

/**
 * Envelope for the universe evaluation. Mirrors the backend
 * `AssetUniverseEvaluationResponse`: `evaluation` is `null` when the universe is
 * empty (nothing to assess yet).
 */
export interface AssetUniverseEvaluationResponse {
  evaluation: AssetUniverseEvaluation | null;
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
  /**
   * The asset's SEC EDGAR fundamentals when a record exists (populated for
   * watchlist assets today), or `null` when none has been fetched. Surfacing it
   * never triggers a fetch.
   */
  fundamentals: AssetFundamentals | null;
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
 * Which asset bucket a recommendation run targets. `universe` (default) adds
 * tradable universe members; `watchlist` seeks emerging companies added as
 * watchlist entries. Mirrors the backend `RunTarget` enum.
 */
export type RunTarget = 'universe' | 'watchlist';

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
  /** The asset bucket this run targeted (defaults to `universe`). */
  target: RunTarget;
  /** The AI model this run executed on (a shared-catalog model id). */
  model: string;
}

/**
 * Request body for `POST /api/v1/recommendations`. `count` is the number of
 * assets to find (integer >= 1); `categories` limits the search (>= 1 entry).
 * Responds 202 with the created `RecommendationRun` or 422 on validation failure.
 */
export interface RecommendationRunCreate {
  count: number;
  categories: AssetCategory[];
  /**
   * Which asset bucket to add results to. Omitted/`universe` targets the
   * tradable universe; `watchlist` seeks emerging companies. A `watchlist`
   * target rejects any non-stock category (422).
   */
  target?: RunTarget;
  /**
   * AI model (a shared-catalog model id) to run on. Omit to use the configured
   * default recommender model; an id outside the catalog is rejected (422).
   */
  model?: string;
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
  archived_at: string | null;
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
  portfolio_name: string | null;
  strategy_key: string;
  status: string;
  allocated_capital: number;
  /** Total capital contributed to date (initial allocation + every increase). */
  contributed_capital: number;
  max_allocation_pct: number;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  total_trades: number;
  total_pnl: number;
  session_metadata: Record<string, unknown> | null;
  schedule_mode: string;
  /**
   * How often this session rebalances (frozen at build time). Derived from
   * `schedule_mode`; legacy sessions on a non-rebalancing mode read as `'daily'`.
   */
  rebalance_cadence: 'daily' | 'weekly' | 'monthly';
  archived_at: string | null;
  /** The rebalance-prompt version frozen onto this session at build time. */
  rebalance_prompt_version: number;
  /** The benchmark id this session is compared against (a catalog id, e.g. `SP500`). */
  benchmark: string;
  /** The AI model this session's runs execute on (a model-catalog id, frozen at build time). */
  model: string;
  /**
   * The session's current asset scope (mutable). Legacy sessions without a stored
   * scope read as `'both'`. Narrowing this liquidates now-out-of-scope holdings.
   */
  asset_types: 'stocks' | 'crypto' | 'both';
  /**
   * Whether this session opted into the technical-indicator trend strategy
   * (frozen at build time). False for sessions built before this option existed.
   */
  use_technical_indicators: boolean;
  /**
   * Whether this session opted into the hard stop-loss (frozen at build time).
   * False for sessions built before this option existed.
   */
  stop_loss_enabled: boolean;
  /**
   * The frozen stop-loss threshold as a fraction (e.g. `0.15` = 15%), or `null`
   * when the stop-loss is disabled.
   */
  stop_loss_pct: number | null;
  /**
   * Whether this session opted into the deterministic risk guardrails (frozen at
   * build time). False for sessions built before this option existed.
   */
  risk_guardrails_enabled: boolean;
  /**
   * The frozen guardrail parameters as fractions (e.g. `0.25` = 25%), or `null`
   * when the guardrails are disabled. The per-asset cap reuses `max_allocation_pct`
   * above (`1.0` = no cap when guardrails off).
   */
  max_asset_class_pct: number | null;
  min_positions: number | null;
  max_invested_pct: number | null;
  /**
   * Whether this session opted into learning feedback (frozen at build time):
   * the rebalance agent is informed of the session's own recent prior-run
   * outcomes. False for sessions built before this option existed.
   */
  learning_feedback_enabled: boolean;
  /**
   * The frozen learning window (number of recent daily runs summarized for the
   * rebalance agent), or `null` when learning feedback is disabled.
   */
  learning_feedback_window: number | null;
  /**
   * Whether this session opted into the company-fundamentals strategy (frozen at
   * build time): each rebalance attaches a per-ticker company-fundamentals block to
   * the agent's candidates and holdings. False for sessions built before this
   * option existed.
   */
  use_fundamentals: boolean;
  /**
   * Whether this session opted into the learned price-direction (price-ML) strategy
   * (frozen at build time): each rebalance attaches a per-ticker learned
   * price-direction block to the agent's candidates and holdings. False for sessions
   * built before this option existed.
   */
  use_price_ml: boolean;
  /**
   * Whether this session opted into the news-sentiment strategy (frozen at build time):
   * each rebalance attaches a per-ticker recency-weighted news-tone block to the agent's
   * candidates and holdings. False for sessions built before this option existed.
   */
  use_news_sentiment: boolean;
  /**
   * Whether this session's candidate universe includes the user's watchlist-membership
   * assets (frozen at build time). False for sessions built before this option existed.
   */
  include_watchlist: boolean;
  /**
   * Live net-asset value (cash plus open positions marked to current quotes, net of
   * fees), computed at request time. Point-in-time, not range-scoped.
   */
  current_value: number;
  /** Cumulative (all-time) gross closed-lot realised P&L. Equal to `total_pnl`. */
  realised_pnl: number;
  /** Live mark-to-market unrealised P&L on open positions (all-time basis). */
  unrealised_pnl: number;
}

/** One entry in the fixed benchmark catalog. Mirrors `BenchmarkCatalogEntry`. */
export interface BenchmarkCatalogEntry {
  id: string;
  name: string;
}

/** One selectable AI model in the fixed catalog. Mirrors `ModelCatalogEntry`. */
export interface ModelCatalogEntry {
  id: string;
  name: string;
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
  /** The AI run (build/rebalance event) that opened this trade; null for non-AI. */
  ai_portfolio_event_id: string | null;
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

/** Result of reconciling one session's non-terminal orders. Mirrors `PaperTradeReconcileRead`. */
export interface PaperTradeReconcileResult {
  trades_seen: number;
  trades_reconciled: number;
  trades_filled: number;
  trades_basis_corrected: number;
  /** The session's trades refreshed after reconciliation. */
  trades: PaperTrade[];
}

/** A record of a single session run. Mirrors `SessionRunRead`. */
export interface SessionRun {
  id: string;
  session_id: string;
  /** The AI build/rebalance event that produced this run, or null for stop-loss and scheduled/manual runs. */
  ai_portfolio_event_id: string | null;
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
  /** The AI rebalance event that closed this position; null for non-AI. */
  ai_portfolio_event_id: string | null;
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

/** One position's line in a value snapshot's breakdown. */
export interface SessionValueSnapshotPosition {
  ticker: string;
  quantity: number;
  price: number;
  market_value: number;
  unrealized_pnl: number;
  return_pct: number;
  [key: string]: unknown;
}

/** An end-of-day portfolio-value snapshot. Mirrors `SessionValueSnapshotRead`. */
export interface SessionValueSnapshot {
  id: string;
  session_id: string;
  /** ISO date (YYYY-MM-DD) the snapshot values the session as of. */
  snapshot_date: string;
  total_value: number;
  cash_value: number;
  positions_value: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  positions: SessionValueSnapshotPosition[];
  created_at: string;
  /**
   * The session's benchmark value rebased to the session start (allocated capital
   * on the first snapshot date). Null when the benchmark has no stored price on or
   * before this snapshot's date.
   */
  benchmark_value: number | null;
}

/** A session's value snapshots (oldest first) plus the matching total. */
export interface SessionValueHistoryResponse {
  items: SessionValueSnapshot[];
  total: number;
}

/** One value point in a comparison series. Mirrors `SessionValueComparisonPoint`. */
export interface SessionValueComparisonPoint {
  /** ISO date (YYYY-MM-DD) of the snapshot. */
  snapshot_date: string;
  total_value: number;
}

/**
 * One session's value history for the multi-session comparison chart.
 * Mirrors `SessionValueComparisonSeries`. `label` is the portfolio name falling
 * back to the strategy key; `points` is oldest-first and may be empty.
 */
export interface SessionValueComparisonSeries {
  session_id: string;
  label: string;
  allocated_capital: number;
  points: SessionValueComparisonPoint[];
}

/** Every non-archived session with its value points. Mirrors `SessionValueComparisonResponse`. */
export interface SessionValueComparisonResponse {
  sessions: SessionValueComparisonSeries[];
}

/**
 * Performance attribution for one sector/category group within a session.
 * Mirrors `SessionGroupPerformance`. `key` is the sector/category name or a
 * "No sector"/"Unknown" sentinel bucket; `return_pct` is null when the group's
 * invested cost basis is zero (unavailable).
 */
export interface SessionGroupPerformance {
  key: string;
  market_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  return_pct: number | null;
}

/** A session's P&L attributed by sector and by category. Mirrors `SessionSectorPerformanceRead`. */
export interface SessionSectorPerformance {
  by_sector: SessionGroupPerformance[];
  by_category: SessionGroupPerformance[];
}

/** A session's live performance KPIs. Mirrors `PaperTradingSessionKpisRead`. */
export interface PaperTradingSessionKpis {
  current_value: number;
  /** Uninvested cash in the session (current value minus marked-to-market positions). */
  unallocated_cash: number;
  realised_pnl: number;
  unrealised_pnl: number;
  /** Cumulative transaction cost charged to date. */
  total_fees: number;
  /**
   * Number of recorded orders (trades) divided by the number of recorded daily
   * value snapshots. Null until the session has at least one snapshot.
   */
  daily_avg_orders: number | null;
  total_return: number;
  total_return_pct: number;
  /** Null until the session has enough daily history to compute it. */
  sharpe_ratio: number | null;
  /** The session's benchmark id (a catalog id, e.g. `SP500`). */
  benchmark: string;
  /**
   * The benchmark's buy-and-hold fractional return over the session period, from
   * stored prices. Null when the benchmark has insufficient stored prices.
   */
  benchmark_return_pct: number | null;
  /**
   * `total_return_pct − benchmark_return_pct`. Null when the benchmark return is
   * unavailable.
   */
  excess_return_pct: number | null;
  /**
   * The excess as an absolute amount (`excess_return_pct × allocated_capital`): the
   * session's net-of-fees dollar gain minus the benchmark's dollar gain on the same
   * capital. Null when the benchmark return is unavailable.
   */
  excess_return: number | null;
  /**
   * Largest peak-to-trough decline of the daily NAV series, as a non-negative
   * fraction. Null when the session has no value snapshots.
   */
  max_drawdown: number | null;
  /** Fraction of closed positions with realised P&L > 0. Null with none closed. */
  win_rate: number | null;
  /** Mean realised P&L of winning closed positions. Null with no winners. */
  average_win: number | null;
  /** Mean realised P&L of losing closed positions. Null with no losers. */
  average_loss: number | null;
  /** Largest single winning closed-position P&L. Null with none closed. */
  best_trade: number | null;
  /** Largest single losing closed-position P&L (signed). Null with none closed. */
  worst_trade: number | null;
  /**
   * Cumulative AI (LLM) cost in USD attributed to this session's rebalance runs,
   * from the model proxy's spend log. Null when the cost source is unconfigured or
   * has no attributed spend for the session.
   */
  ai_cost_usd: number | null;
}

// --------------------------------------------------------------------------- //
// AI-managed portfolio
// --------------------------------------------------------------------------- //

/** Which AI job an event records. Mirrors the backend `EventType` enum. */
export type AIEventType = 'build' | 'rebalance' | 'close';

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
 * `allocated_capital` 10000, `risk_profile` "balanced", `asset_types` "both".
 * Every built session is enrolled in daily rebalancing (no opt-out).
 */
export interface AIPortfolioBuildRequest {
  allocated_capital?: number;
  risk_profile?: string;
  /** Which asset categories the portfolio may hold. Defaults to `both`. */
  asset_types?: 'stocks' | 'crypto' | 'both';
  /**
   * How often the session rebalances, frozen at build time. One of `daily`,
   * `weekly`, or `monthly`. Defaults to `daily`; a value outside this set is
   * rejected (422).
   */
  rebalance_cadence?: 'daily' | 'weekly' | 'monthly';
  /** Benchmark id to compare the session against. Defaults to `SP500`. */
  benchmark?: string;
  /**
   * AI model id (a model-catalog id) the session's runs execute on, frozen on the
   * session. Defaults to the configured default model; an out-of-catalog id is
   * rejected (422).
   */
  model?: string;
  /**
   * Opt this portfolio into the technical-indicator trend strategy (frozen at
   * build time). When enabled, both the build and daily rebalances hard-filter
   * candidates through the trend gate and attach holdings reversal context.
   * Defaults to off (opt-in).
   */
  use_technical_indicators?: boolean;
  /**
   * Opt this portfolio into the company-fundamentals strategy (frozen at build
   * time). When enabled, each rebalance attaches a per-ticker company-fundamentals
   * block to the agent's candidates and holdings. Defaults to off (opt-in).
   */
  use_fundamentals?: boolean;
  /**
   * Opt this portfolio into the learned price-direction (price-ML) strategy (frozen
   * at build time). When enabled, each rebalance attaches a per-ticker learned
   * price-direction block to the agent's candidates and holdings. Defaults to off
   * (opt-in).
   */
  use_price_ml?: boolean;
  /**
   * Opt this portfolio into the news-sentiment strategy (frozen at build time). When
   * enabled, each rebalance attaches a per-ticker recency-weighted news-tone block to
   * the agent's candidates and holdings. Defaults to off (opt-in).
   */
  use_news_sentiment?: boolean;
  /**
   * Opt this portfolio into including the user's watchlist-membership assets in the
   * candidate universe the AI picks from (frozen at build time). When enabled, each
   * rebalance assembles candidates from the union of universe- and watchlist-membership
   * assets. Defaults to off (opt-in).
   */
  include_watchlist?: boolean;
  /**
   * Opt this portfolio into a hard stop-loss (frozen at build time). When
   * enabled, each open position is sold in whole when its market price falls to
   * or below `avg_cost × (1 − stop_loss_pct)`. Defaults to off (opt-in).
   */
  stop_loss_enabled?: boolean;
  /**
   * Per-session stop-loss threshold as a fraction (e.g. `0.15` = 15%). Frozen at
   * build time. Defaults to the server-side default when enabled without one.
   */
  stop_loss_pct?: number | null;
  /**
   * Opt this portfolio into the deterministic risk guardrails (frozen at build
   * time). When enabled the target-weight vector is clamped so no asset/class
   * exceeds its cap and the invested fraction stays within the ceiling. Defaults
   * to off (opt-in).
   */
  risk_guardrails_enabled?: boolean;
  /**
   * Maximum fraction of capital for a single asset (e.g. `0.25` = 25%). Applies
   * only when `risk_guardrails_enabled`; defaults to the server-side default when
   * enabled without one.
   */
  max_allocation_pct?: number | null;
  /** Maximum fraction of capital for a single asset class. As above. */
  max_asset_class_pct?: number | null;
  /** Minimum number of positions the AI is asked to hold. As above. */
  min_positions?: number | null;
  /** Maximum invested fraction; the remainder is held as cash. As above. */
  max_invested_pct?: number | null;
  /**
   * Opt this portfolio into learning feedback (frozen at build time): the
   * rebalance agent is shown the session's own recent prior-run outcomes.
   * Defaults to off (opt-in).
   */
  learning_feedback_enabled?: boolean;
  /**
   * Learning window — number of recent daily runs summarized for the rebalance
   * agent. Applies only when `learning_feedback_enabled`; defaults to the
   * server-side default when enabled without one.
   */
  learning_feedback_window?: number | null;
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
  /**
   * Freshly-built sessions deferred because their build orders have not yet
   * filled; picked up by a later trigger once they settle.
   */
  skipped_awaiting_build_fill: string[];
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
  /**
   * The run's research transcript: one entry per web search the agent performed.
   * Null when the run did no research (or on legacy rows before capture existed).
   */
  research: AIResearchEntry[] | null;
  /**
   * The run's trend-decision context: candidates dropped by the trend gate (with
   * reasons) and the indicator annotations handed to the AI for surviving
   * candidates and current holdings. Null for runs that performed no gating (e.g.
   * a session frozen to a pre-trend prompt version).
   */
  trend_context: AITrendContext | null;
  /**
   * The AI model that produced this run (a model-catalog id). Null for historical
   * events and runs that failed before reaching the agent.
   */
  model: string | null;
  error: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
}

/**
 * One web search the agent performed during a run: the `query` it issued, the
 * trimmed `results` payload (null when the search errored or was budget-capped),
 * and an `error` message when the search did not return usable results.
 */
export interface AIResearchEntry {
  query: string;
  results: Record<string, unknown> | null;
  error: string | null;
}

/** A candidate dropped by the trend gate, with the reason it failed. */
export interface AITrendDroppedCandidate {
  ticker: string;
  reason: string;
}

/** A surviving candidate handed to the AI, with its indicator annotation. */
export interface AITrendCandidate {
  ticker: string;
  indicators: Record<string, unknown> | null;
}

/** A current holding handed to the AI, with its indicators and reversal flags. */
export interface AITrendHolding {
  ticker: string;
  indicators: Record<string, unknown> | null;
  reversal_flags: Record<string, unknown> | null;
}

/**
 * The per-run trend-decision context recorded on an AI event. Mirrors the backend
 * `trend_context` blob: what the gate dropped and what was handed to the AI.
 */
export interface AITrendContext {
  dropped_candidates: AITrendDroppedCandidate[];
  candidates: AITrendCandidate[];
  holdings: AITrendHolding[];
}

/** A page of AI runs plus the matching total. Mirrors `AIPortfolioRunListResponse`. */
export interface AIPortfolioRunListResponse {
  items: AIPortfolioEvent[];
  total: number;
}

/**
 * A page of a session's AI-portfolio events plus the matching total. Mirrors the
 * backend `AIPortfolioEventListResponse` envelope for the session events read.
 */
export interface AIPortfolioEventListResponse {
  items: AIPortfolioEvent[];
  total: number;
}

/**
 * One AI run with the trades it opened and the positions it closed. Mirrors the
 * backend `AIPortfolioRunDetail` schema for `GET /ai-portfolio/runs/{event_id}`.
 */
export interface AIPortfolioRunDetail {
  event: AIPortfolioEvent;
  trades: PaperTrade[];
  closed_positions: ClosedPosition[];
  /** The rebalance-prompt version frozen on the run's session, or null if it has none. */
  rebalance_prompt_version: number | null;
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

// --------------------------------------------------------------------------- //
// Dashboard overview (range-scoped)
// --------------------------------------------------------------------------- //

/**
 * The global broker-style range selector. Wire values mirror the backend
 * `DashboardRange` enum and are sent verbatim as the `range` query param.
 */
export type DashboardRange = '1D' | '1W' | '1M' | 'YTD' | '1Y' | 'Max';

/** All ranges in display order, for rendering the selector. */
export const DASHBOARD_RANGES: readonly DashboardRange[] = [
  '1D',
  '1W',
  '1M',
  'YTD',
  '1Y',
  'Max',
] as const;

/** One (date, value) point of a session's range-windowed value series. */
export interface DashboardSessionValuePoint {
  date: string; // ISO YYYY-MM-DD
  value: number;
}

/**
 * One capital contribution to a session: the opening capital (effective at its
 * start date) or a later capital increase. The client combines these with each
 * benchmark index's prices to build the buy-and-hold benchmark comparison line.
 * Mirrors `DashboardSessionContribution`.
 */
export interface DashboardSessionContribution {
  effective_date: string; // ISO YYYY-MM-DD
  amount: number;
}

/** A single active session's range-scoped performance. Mirrors `DashboardSessionPerformance`. */
export interface DashboardSessionPerformance {
  id: string;
  label: string;
  /**
   * Which engine runs this session: an AI-managed portfolio (`ai`) or a
   * deterministic strategy bot (`bot`). Drives the leaderboard/legend badge and
   * where a row's link points (`/portfolios/:id` vs `/bots/:id`).
   */
  kind: 'ai' | 'bot' | 'orchestrator';
  allocated_capital: number;
  current_value: number;
  pnl: number;
  /** Range-relative realised P&L: summed closed-lot realised P&L within the range (cumulative for `Max`). */
  realised_pnl: number;
  /** Range-relative unrealised P&L: current live unrealised minus the range-start snapshot baseline. */
  unrealised_pnl: number;
  fees: number;
  points: DashboardSessionValuePoint[];
  contributions: DashboardSessionContribution[];
  /**
   * Since-inception current USD value of a contribution-aware buy-and-hold of this
   * session's contributions in its own benchmark; `null` when unpriceable. Range-
   * independent. The client aggregates it into the live excess-return tile.
   */
  benchmark_value: number | null;
}

/** A reference to a single AI run for the automation summary. */
export interface DashboardAutomationRun {
  id: string;
  event_type: string;
  status: string;
  created_at: string; // ISO datetime
  session_id: string | null;
}

/** Health of the AI rebalance automation, scoped to the selected range. */
export interface DashboardAutomationSummary {
  latest_run: DashboardAutomationRun | null;
  in_flight: boolean;
  failed_in_range: number;
  next_run_approx: string; // ISO datetime
  next_run_is_approximate: boolean;
}

/** One AI run in the recent-activity feed. */
export interface DashboardActivityEntry {
  id: string;
  session_id: string | null;
  session_label: string | null;
  kind: string;
  status: string;
  created_at: string; // ISO datetime
}

/** Current composition of the asset universe (range-independent). */
export interface DashboardUniverseBalance {
  total: number;
  eligible: number;
  ineligible: number;
  sectors_count: number;
  top_sector_key: string | null;
  top_sector_share: number;
  top_category_key: string | null;
  top_category_share: number;
}

/** One asset's market return over the range, for the performer rankings. */
export interface DashboardPerformerEntry {
  asset_id: number;
  ticker: string;
  name: string | null;
  return_pct: number;
}

/** Best and worst tracked assets by market return over the range. */
export interface DashboardUniversePerformers {
  best: DashboardPerformerEntry[];
  worst: DashboardPerformerEntry[];
}

/** One (date, price) point of a benchmark index's closing-price series. */
export interface DashboardBenchmarkPricePoint {
  date: string; // ISO YYYY-MM-DD
  price: number;
}

/**
 * One catalog benchmark's price series for the combined-equity overlay. `points`
 * are raw index closes (not pre-converted to dollars); the client combines them
 * with the selected sessions' contributions to build a buy-and-hold dollar line
 * summed over those sessions. An index with no stored prices in range has an empty
 * `points` list. Mirrors `DashboardBenchmarkSeries`.
 */
export interface DashboardBenchmarkSeries {
  benchmark_id: string;
  name: string;
  points: DashboardBenchmarkPricePoint[];
}

/** The full range-scoped overview from `GET /api/v1/dashboard/overview`. */
export interface DashboardOverview {
  range: DashboardRange;
  sessions: DashboardSessionPerformance[];
  automation: DashboardAutomationSummary;
  recent_activity: DashboardActivityEntry[];
  universe_balance: DashboardUniverseBalance;
  universe_performers: DashboardUniversePerformers;
  benchmark_series: DashboardBenchmarkSeries[];
  /** Whether the US equity market is currently open (default-open on clock failure). */
  market_open: boolean;
}

/** One portfolio's all-time cumulative AI cost (null when unavailable). */
export interface DashboardPortfolioAiCost {
  session_id: string;
  label: string;
  ai_cost_usd: number | null;
}

/** One active bot orchestrator's all-time AI cost (the sum of its runs). */
export interface DashboardOrchestratorAiCost {
  orchestrator_id: string;
  label: string;
  ai_cost_usd: number | null;
}

/** Per-portfolio and per-orchestrator AI cost breakdown from `GET /api/v1/dashboard/ai-costs`. */
export interface DashboardAiCosts {
  portfolios: DashboardPortfolioAiCost[];
  orchestrators: DashboardOrchestratorAiCost[];
  total_ai_cost_usd: number | null;
}

// --- Technical-indicator configuration (read-only) -------------------------

/** One period/lookback parameter defining an indicator. */
export interface IndicatorParam {
  name: string;
  value: number;
}

/** A single indicator in the computed set with its defining parameters. */
export interface IndicatorInfo {
  key: string;
  label: string;
  params: IndicatorParam[];
}

/**
 * One trend-gate condition. `threshold` is null for comparisons between two
 * indicators (e.g. SMA50 > SMA200).
 */
export interface GateCondition {
  description: string;
  threshold: number | null;
}

/** The deterministic uptrend gate: regime + momentum conditions and rules. */
export interface TrendGateConfig {
  description: string;
  regime: GateCondition[];
  momentum: GateCondition[];
  obv_bonus: string;
  missing_indicator_rule: string;
}

/** One reversal flag and what sets it. */
export interface ReversalFlagInfo {
  key: string;
  label: string;
  description: string;
}

/** The reversal-flag definitions plus their tunable thresholds. */
export interface ReversalFlagsConfig {
  flags: ReversalFlagInfo[];
  rsi_overbought: number;
  slope_flatten_eps: number;
}

/** The full read-only config from `GET /api/v1/technical-indicators/config`. */
export interface TechnicalIndicatorConfig {
  indicators: IndicatorInfo[];
  trend_gate: TrendGateConfig;
  reversal_flags: ReversalFlagsConfig;
}

/**
 * One watchlist asset's short-window technical profile. Mirrors the backend
 * `WatchlistIndicatorRead`. Only the short-window (momentum / mean-reversion)
 * subset is carried — the long-window indicators and the uptrend trend-gate
 * verdict are deliberately omitted, as they are not a meaningful signal for
 * emerging names. When `insufficient_history` is `true` (fewer than the
 * minimum-bars floor, or no snapshot yet) the value fields are `null`.
 */
export interface WatchlistIndicator {
  asset_id: number;
  ticker: string;
  trading_date: string | null;
  bar_count: number | null;
  insufficient_history: boolean;
  rsi_14: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  ema_20: number | null;
  bb_pctb: number | null;
  bb_width: number | null;
  hvol_20: number | null;
  vol_ratio_50: number | null;
  obv_change_20d: number | null;
  rev_macd_hist_rollover: boolean;
  rev_rsi_rollover: boolean;
  rev_return_decel: boolean;
  rev_obv_price_divergence: boolean;
}

/** The batched watchlist indicators response plus the minimum-bars floor. */
export interface WatchlistIndicatorsResponse {
  min_bars: number;
  items: WatchlistIndicator[];
}

/**
 * A single asset's short-window technical profile with the minimum-bars floor.
 * Mirrors the backend `AssetIndicatorResponse` for
 * `GET /api/v1/technical-indicators/assets/{ticker}`. Serves assets of any
 * membership. `indicator` is `null` only when the asset has no stored snapshot;
 * an asset below the floor is returned with `insufficient_history` set.
 */
export interface AssetIndicatorResponse {
  min_bars: number;
  indicator: WatchlistIndicator | null;
}

// --- System status ---------------------------------------------------------

/**
 * Live-probe status of a single external backend. Carries only booleans and
 * non-secret identifiers — never a key/secret/token. `reachable` is `null` when
 * no probe was performed (unconfigured, or broker stub mode); `true`/`false`
 * reflect the live probe.
 */
export interface SystemBackendStatus {
  name: string;
  configured: boolean;
  identifier: string | null;
  reachable: boolean | null;
  latency_ms: number | null;
  detail: string | null;
}

/** Response of `GET /api/v1/system/status`: one entry per external backend. */
export interface SystemStatusResponse {
  backends: SystemBackendStatus[];
}

// --- Strategy bots ----------------------------------------------------------

/** A registered bot strategy, its explanation, and its default parameter schema. Mirrors `BotStrategyCatalogEntry`. */
export interface BotStrategyCatalogEntry {
  key: string;
  display_name: string;
  explanation: string;
  required_history: number;
  /** JSON Schema of the strategy's parameters (from the backend Pydantic model). */
  params_schema: Record<string, unknown>;
}

/**
 * A fixed course-recipe bot preset: one strategy with its course parameters and
 * risk controls. Risk values are fractions (0.01 = 1%); `null` take-profit /
 * stop-loss means off. Mirrors `BotPresetRead`.
 */
export interface BotPreset {
  key: string;
  display_name: string;
  description: string;
  course_ref: string;
  strategy_key: string;
  strategy_params: Record<string, unknown>;
  take_profit_pct: number | null;
  stop_loss_pct: number | null;
  drawdown_stop_pct: number;
  is_default: boolean;
}

/** One eligible universe equity in a bot session's tradable symbol set. Mirrors `BotSymbolRead`. */
export interface BotSymbol {
  asset_id: number;
  ticker: string;
  alpaca_symbol: string;
}

/** One open long position held by a bot session. Mirrors `BotPositionRead`. */
export interface BotPosition {
  asset_id: number;
  ticker: string;
  alpaca_symbol: string;
  quantity: number;
  avg_price: number;
  opened_at: string;
}

/** A strategy-bot session with its configuration and running totals. Mirrors `BotSessionRead`. */
export interface BotSession {
  id: string;
  strategy_key: string;
  label: string | null;
  status: string;
  benchmark: string;
  initial_capital: number;
  allocated_capital: number;
  cash: number;
  /** Live value: cash plus marked-to-market positions (freshest observation, cost fallback). */
  current_value: number;
  /** End-of-day value: the latest daily snapshot total value, or null until a snapshot exists. */
  eod_value: number | null;
  sizing_method: string;
  risk_pct: number;
  atr_period: number;
  atr_k: number;
  max_position_pct: number;
  max_positions: number;
  strategy_params: Record<string, unknown>;
  take_profit_pct: number | null;
  stop_loss_pct: number | null;
  drawdown_stop_pct: number;
  cash_buffer_pct: number;
  peak_value: number;
  /** The preset the session started from, or null for a custom configuration. */
  preset_key: string | null;
  /** Whether the session's params / risk controls were changed from its preset. */
  preset_customized: boolean;
  /** Who created the session (`manual` for the build form, `orchestrator` when deployed by one). */
  origin: string;
  /** The name the bot is shown under (label, else preset/strategy name · traded set). */
  display_name: string;
  /** The bot orchestrator that deployed the session, or null for manual sessions. */
  orchestrator_id: string | null;
  /** That orchestrator's label, or null. */
  orchestrator_label: string | null;
  symbols: BotSymbol[];
  positions: BotPosition[];
  total_trades: number;
  realised_pnl: number;
  total_fees: number;
  created_at: string;
  updated_at: string;
  last_tick_at: string | null;
  archived_at: string | null;
}

/** A list of strategy-bot sessions plus the matching total. Mirrors `BotSessionListResponse`. */
export interface BotSessionListResponse {
  items: BotSession[];
  total: number;
}

/** Performance KPIs for a bot session, from its own ledger + snapshots. Mirrors `BotKpisRead`. */
export interface BotKpis {
  current_value: number;
  /** Available (free, uninvested) cash — the balance not deployed in open positions. */
  cash: number;
  allocated_capital: number;
  total_return: number;
  total_return_pct: number;
  realised_pnl: number;
  unrealised_pnl: number;
  total_fees: number;
  total_trades: number;
  max_drawdown: number;
  sharpe_ratio: number | null;
  /** Best and worst closed round-trip by realized P&L; null until a position has been closed. */
  best_trade: TradeExtreme | null;
  worst_trade: TradeExtreme | null;
  /** The session's benchmark id. */
  benchmark: string;
  /** The benchmark's since-inception buy-and-hold return fraction; null until a snapshot exists. */
  benchmark_return_pct: number | null;
  /** The session's excess return fraction (total return minus the benchmark's); null until a snapshot exists. */
  excess_return_pct: number | null;
  /** End-of-day value: the latest daily snapshot total value, or null until a snapshot exists. */
  eod_value: number | null;
  /** When the current value was captured (intraday point or daily snapshot); null before any observation. */
  value_as_of: string | null;
  /** True when the current value came from an intraday value point. */
  value_is_intraday: boolean;
}

/** A single closed round-trip trade: its ticker, realized P&L, and exact fills. Mirrors `TradeExtremeRead`. */
export interface TradeExtreme {
  ticker: string;
  realised_pnl: number;
  quantity: number;
  entry_price: number;
  entry_at: string;
  exit_price: number;
  exit_at: string;
}

/** The curated stats block of a stopped session's summary. Mirrors `SessionSummaryStatsRead`. */
export interface SessionSummaryStats {
  /** Why the session stopped (`'drawdown_kill_switch'` | `'manual'`); null if not recorded. */
  stop_reason: string | null;
  stopped_at: string | null;
  started_at: string;
  lifespan_days: number;
  final_value: number;
  allocated_capital: number;
  total_return: number;
  total_return_pct: number;
  realised_pnl: number;
  peak_value: number;
  max_drawdown: number;
  trade_count: number;
  /** Share of closed round-trips with positive realized P&L; null with no closed trades. */
  win_rate: number | null;
  best_trade: TradeExtreme | null;
  worst_trade: TradeExtreme | null;
  benchmark: string;
  benchmark_return_pct: number | null;
  excess_return_pct: number | null;
}

/** A stopped session's summary: its stats block plus the cached AI narrative. Mirrors `BotSessionSummaryRead`. */
export interface BotSessionSummary {
  stats: SessionSummaryStats;
  /** The cached AI narrative (markdown); null when not yet generated or the agent failed. */
  narrative: string | null;
  model: string | null;
  generated_at: string | null;
}

/** A single fill recorded by the bot engine. Mirrors `BotTradeRead`. */
export interface BotTrade {
  id: string;
  bot_session_id: string;
  side: string;
  ticker: string;
  quantity: number;
  filled_price: number | null;
  fees: number;
  reason: string | null;
  order_id: string | null;
  status: string;
  created_at: string;
}

/** A list of bot trades plus the matching total. Mirrors `BotTradeListResponse`. */
export interface BotTradeListResponse {
  items: BotTrade[];
  total: number;
}

/** Resolution of a bot session's value-history read. Mirrors `BotValueResolution`. */
export type BotValueResolution = '5min' | 'hourly' | 'daily' | 'monthly';

/** One timestamped value-history point for a bot session. Mirrors `BotValuePointRead`. */
export interface BotValuePoint {
  timestamp: string; // ISO datetime
  total_value: number;
  realised_pnl: number;
  unrealised_pnl: number;
}

/** A bot session's value history at a resolution plus the total. Mirrors `BotValueHistoryResponse`. */
export interface BotValueHistoryResponse {
  items: BotValuePoint[];
  total: number;
  resolution: BotValueResolution;
}

/** Request to create a strategy-bot session. Mirrors `BotSessionCreateRequest`. */
export interface BotSessionCreateRequest {
  strategy_key?: string | null;
  /** Start from this preset; omitted params / risk fields take the preset's values. */
  preset_key?: string | null;
  tickers?: string[] | null;
  whole_universe?: boolean;
  initial_capital: number;
  benchmark: string;
  strategy_params?: Record<string, unknown> | null;
  label?: string | null;
  take_profit_pct?: number | null;
  stop_loss_pct?: number | null;
  drawdown_stop_pct?: number | null;
  cash_buffer_pct?: number | null;
  sizing_method?: string | null;
  risk_pct?: number | null;
  atr_period?: number | null;
  atr_k?: number | null;
  max_position_pct?: number | null;
  max_positions?: number | null;
}

// --- Bot orchestrator ------------------------------------------------------

/** Request to deploy a bot orchestrator. Mirrors `BotOrchestratorCreateRequest`. */
export interface BotOrchestratorCreateRequest {
  label: string;
  capital: number;
  max_parallel_bots: number;
  /** Max share (0, 1] of the orchestrator's value one bot may receive. */
  max_bot_share: number;
  max_tickers_per_bot: number;
  cadence: string;
  model?: string | null;
  benchmark: string;
}

/** One applied or rejected action recorded on a decision run. */
export interface OrchestratorAction {
  kind: 'stop' | 'deploy';
  /** Applied actions: the stopped or deployed bot. */
  bot_id?: string;
  preset_key?: string | null;
  tickers?: string[];
  capital?: number;
  rationale?: string;
  /** Applied stops carry the AI's reason; rejections carry the validation reason. */
  reason?: string;
  /** Rejected actions: the AI's original action. */
  action?: Record<string, unknown>;
}

/** A decision run as listed in the run history. Mirrors `OrchestratorRunSummaryRead`. */
export interface OrchestratorRunSummary {
  id: string;
  trigger: 'scheduled' | 'manual' | string;
  status: 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'skipped' | string;
  model: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  market_summary: string | null;
  applied: OrchestratorAction[];
  rejected: OrchestratorAction[];
  /** The AI call's token usage; null when the run ended before the AI answered. */
  usage: OrchestratorRunUsage | null;
  /** The run's AI cost in USD; null when the cost source is unavailable. */
  ai_cost_usd: number | null;
}

/** Token usage of one decision run's AI call. */
export interface OrchestratorRunUsage {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

/** A decision run in full. Mirrors `OrchestratorRunRead`. */
export interface OrchestratorRun extends OrchestratorRunSummary {
  orchestrator_id: string;
  prompt_version: number | null;
  briefing: Record<string, unknown> | null;
  decision: Record<string, unknown> | null;
  research: Record<string, unknown>[];
}

/** One bot an orchestrator deployed. Mirrors `OrchestratorBotRead`. */
export interface OrchestratorBot {
  id: string;
  /** The name the bot is shown under (label, else preset/strategy name · traded set). */
  display_name: string;
  label: string | null;
  preset_key: string | null;
  preset_name: string | null;
  strategy_key: string;
  tickers: string[];
  status: string;
  stop_reason: string | null;
  initial_capital: number;
  current_value: number;
  total_return_pct: number;
  open_positions: number;
  created_at: string;
  stopped_at: string | null;
  capital_returned_at: string | null;
}

/** An orchestrator with computed capital figures. Mirrors `BotOrchestratorRead`. */
export interface BotOrchestrator {
  id: string;
  label: string;
  status: 'active' | 'stopped' | 'archived' | string;
  capital: number;
  free_capital: number;
  allocated_capital: number;
  value: number;
  total_return_pct: number;
  max_parallel_bots: number;
  max_bot_share: number;
  max_tickers_per_bot: number;
  cadence: string;
  model: string;
  benchmark: string;
  active_bots: number;
  liquidating_bots: number;
  created_at: string;
  stopped_at: string | null;
  archived_at: string | null;
  last_run: OrchestratorRunSummary | null;
  /** All-time AI cost in USD (sum of its runs); null when the source is unavailable. */
  ai_cost_usd: number | null;
}

/** An orchestrator plus every bot it deployed. Mirrors `BotOrchestratorDetailRead`. */
export interface BotOrchestratorDetail extends BotOrchestrator {
  bots: OrchestratorBot[];
}

/** Orchestrators plus the total. Mirrors `BotOrchestratorListResponse`. */
export interface BotOrchestratorListResponse {
  items: BotOrchestrator[];
  total: number;
}

/** A page of decision runs plus the total. Mirrors `OrchestratorRunListResponse`. */
export interface OrchestratorRunListResponse {
  items: OrchestratorRunSummary[];
  total: number;
}

// --- Broker-account admin ---------------------------------------------------

/** Live broker account balances. */
export interface AdminAccountFigures {
  cash: number;
  buying_power: number;
  portfolio_value: number;
  currency: string;
}

export type AdminCashContributorKind = 'portfolio' | 'bot' | 'orchestrator' | 'returning_bot';

/** One holder of cash Cadence considers committed. */
export interface AdminCashContributor {
  kind: AdminCashContributorKind;
  id: string;
  label: string;
  amount: number;
}

/** Committed cash vs the account's cash (`difference` = account − committed). */
export interface AdminCashCheck {
  contributors: AdminCashContributor[];
  committed_total: number;
  account_cash: number;
  difference: number;
  shortfall: boolean;
}

/** An open order in the broker account. */
export interface AdminOpenOrder {
  order_id: string | null;
  symbol: string;
  side: string;
  quantity: number;
  order_type: string;
  status: string;
  submitted_at: string | null;
}

export type AdminPositionStatus = 'matched' | 'orphan' | 'shortfall' | 'short';

/** Broker vs Cadence quantity for one symbol, with its orphan classification. */
export interface AdminPosition {
  symbol: string;
  asset_class: string;
  broker_quantity: number;
  cadence_quantity: number;
  orphan_quantity: number;
  market_value: number | null;
  status: AdminPositionStatus;
  pending_order: boolean;
  flattenable: boolean;
}

/** The Admin page payload; sections are empty when the broker is unavailable. */
export interface AdminAccount {
  broker_available: boolean;
  reason: string | null;
  account: AdminAccountFigures | null;
  cash_check: AdminCashCheck | null;
  open_orders: AdminOpenOrder[];
  positions: AdminPosition[];
}

/** Per-symbol result of a flatten action. */
export interface AdminFlattenOutcome {
  symbol: string;
  result: 'sold' | 'skipped' | 'failed';
  quantity: number | null;
  order_id: string | null;
  reason: string | null;
}

export interface AdminFlattenResponse {
  outcomes: AdminFlattenOutcome[];
}
