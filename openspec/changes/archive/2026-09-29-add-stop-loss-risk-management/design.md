## Context

See `proposal.md` — Why. Cadence acts on scheduled crons and holds no intraday
monitoring loop: the only exit signal today is the once-daily AI rebalance. A
meaningful hard stop-loss therefore needs its own, more frequent trigger and a live
price source. Prices for marks already come from `broker.get_quotes` (the same source
the daily value-snapshot job at `paper_trading/service.py:756` and the live KPI mark at
`ai_portfolio/service.py:1379` use). Holdings and weighted-average cost are the ledger's
job (source of truth). Executions and their recording (trade + `SessionRun` + closed
position + `$1` transaction cost) already flow through `ai_portfolio/executor.py`. This
design reuses all of those rather than inventing a parallel path.

The frozen-at-build pattern is established: `rebalance_prompt_version`, the asset scope,
the benchmark, and the just-shipped `use_technical_indicators` flag are each a
non-nullable column mirrored onto the session and honoured by later automated runs. The
stop-loss opt-in and threshold follow that pattern exactly.

## Goals / Non-Goals

**Goals:**
- An opt-in, frozen-at-build hard stop-loss that fully exits a position when its live
  price falls to `avg_cost × (1 − stop_loss_pct)`, evaluated by our own logic.
- A dedicated cron endpoint that scans all active opted-in sessions frequently, dedups
  tickers, and fetches quotes in batched multi-symbol requests.
- Re-entry protection via a per-session cooldown quarantine consumed by the rebalance
  candidate assembly.
- Reuse the existing executor/recording path and the existing notification path.

**Non-Goals (design-level boundaries beyond the proposal's out-of-scope list):**
- No new intraday price cache or streaming feed — each scan pulls latest quotes.
- No change to how the daily rebalance decides trims/exits for held positions (the
  stop-loss is an independent floor, not a rebalance input beyond the quarantine).
- No broker-native stop orders; no per-asset-class threshold; no trailing/drawdown/
  take-profit logic.

## Decisions

### 1. A dedicated cron endpoint, not folded into rebalance
The rebalance runs once a day and only when the market is open; a stop-loss that only
fires then is worthless. A separate `POST` cron endpoint (guarded by the existing
`REBALANCE_CRON_TOKEN` / `X-Cron-Token` mechanism, reusing the same token check as the
rebalance trigger) is registered to fire every few minutes. **Alternative rejected:**
a background timer thread inside the app — Cadence's established pattern is
externally-triggered crons (rebalance, notifications), and an in-process scheduler would
diverge from ops and complicate multi-worker deploys.

Whether to reuse `REBALANCE_CRON_TOKEN` or add a new token: reuse it. It is the same
trust boundary (the scheduler), and a second secret adds ops surface for no security
gain. Documented in the endpoint's requirement as "the shared cron-token secret."

### 2. Our-logic evaluation at scan time
For each opted-in active session, read ledger holdings + weighted-average cost, mark each
position against the batched latest quote, and sell the whole position when
`price ≤ avg_cost × (1 − stop_loss_pct)`. **Alternative rejected:** submitting
broker-native stop orders at buy time — Alpaca stop orders on the paper feed are hard to
keep in sync with our ledger cost basis and with rebalance-driven position changes, and
they bypass our recording/transaction-cost/notification path. Evaluating in our logic
keeps one source of truth and one recording path.

### 3. Batched multi-symbol quotes (implementation detail, not a spec change)
`broker.get_quotes` currently loops one HTTP call per symbol (`broker/alpaca.py`). A
frequent scan across all sessions would blow the Alpaca rate limit. The scan dedups the
union of held tickers across sessions and fetches them in batched multi-symbol requests:
Alpaca equities `GET /v2/stocks/quotes/latest?symbols=…` and crypto
`GET /v1beta3/crypto/us/latest/quotes?symbols=…` both accept comma-separated symbol
lists. This is an internal optimization of the existing `get_quotes` contract (same
inputs/outputs), so it stays in design + tasks and is **not** a spec requirement.
Keep the per-symbol fallback for robustness.

### 4. Sizing/exit reuses the executor
A stop-out is a full sell of the position. Route it through the existing executor sell
path so it records a `PaperTrade` with `signal_type = stop_loss` and **no**
`ai_portfolio_event_id`, a `SessionRun` with a `stop_loss` trigger, and a
`ClosedPosition` with realized P&L, and so the `$1` `TRANSACTION_COST_USD` is charged at
`record_trade` and netted into `total_fees` — all automatically, because those behaviours
already live in the shared path. New enum values: a `stop_loss` `signal_type` and a
`stop_loss` `SessionRun` trigger (constants only, no schema-shape change beyond the
enum's stored string).

### 5. Cooldown quarantine in a small dedicated table
A stopped ticker must not be re-bought by the very next rebalance. Record a per-session
quarantine row `(session_id, ticker, excluded_until)` where `excluded_until` is
`N` trading days ahead (`STOP_LOSS_COOLDOWN_TRADING_DAYS`, default 5). The rebalance
candidate assembly (`daily-rebalancing`) filters out candidates the session does not
hold whose quarantine is unexpired. **Alternative rejected:** a JSON blob on the session
— a table is queryable, lets a row expire independently, and avoids read-modify-write
races when several tickers are stopped in one scan. "Trading days" is approximated the
same way the rest of the app reasons about market days; exact calendar precision is not
required for a cooldown and is called out as a minor assumption.

### 6. Market-status guard mirrors the rebalance executor
Equity sells only when the equities market is open (reuse the executor's existing
market-open check); crypto sells run around the clock. A breached equity position while
the market is closed is simply left for the next scan.

### 7. Threshold is per-session, frozen, with a global default
`stop_loss_enabled: bool` (non-nullable, default false) and `stop_loss_pct: float`
(nullable; meaningful only when enabled) on the session, backfilled off for existing
rows. Global default `STOP_LOSS_DEFAULT_PCT` (e.g. 0.15) in settings applies when the
build enables the stop-loss without an explicit threshold. Single threshold for equities
and crypto (crypto-specific is v2).

### 8. Stop-loss surfaces on the session detail, not the global AI Runs view
The global Runs view lists **AI** runs (build/rebalance `AIPortfolioEvent`s with
reasoning/research). A stop-out has no AI event, reasoning, or research, so forcing it
into that view (and its detail shape) would misrepresent it. Instead the stop-out is
visible where the session's own trades and runs already render — the session detail view
— with the `stop_loss` signal type / trigger making it identifiable. This is a
deliberate refinement of the proposal's "stop-loss runs in the Runs history/detail"
wording; captured in the app-shell delta as session-detail behaviour.

## Risks / Trade-offs

- **Free-tier equity data is IEX-only real-time** → equity stops are approximate (the
  IEX mark can lag the consolidated NBBO). Documented as a known limitation, not a code
  dependency; a paid Alpaca market-data plan tightens it with no code change.
- **Scan frequency vs. rate limits** → batched, deduped quotes keep a scan to a few
  requests; the per-symbol fallback is only for the rare miss. If session/ticker counts
  grow, the batch size may need chunking (noted for tasks).
- **Stop then same-day rebalance re-buy** → mitigated by the cooldown quarantine; the
  window is a settings knob so it can be tuned without a migration.
- **Whole-position exit on a transient wick** → accepted for a first hard stop; trailing
  stops and smoothing are explicit v2 scope. On the free feed a bad print could trigger a
  stop, mitigated only by using latest-quote (not trade) as the primary mark.
- **Partial scan failure** → per-session and per-position try/except so one session's or
  one ticker's failure does not abort the whole scan (mirrors the rebalance trigger's
  best-effort fan-out).
- **Notification failure must not roll back a recorded sale** → send Pushover best-effort
  after the sale is committed, matching the existing rebalance-notification contract.

## Migration Plan

- One Alembic migration on the single linear head: add `stop_loss_enabled`
  (non-nullable, server_default false, backfilled off) and `stop_loss_pct` (nullable) to
  `paper_trading_sessions`; create the `stop_loss_quarantines` table
  (`id`, `session_id` FK, `ticker`, `excluded_until`, `created_at`; index on
  `(session_id, ticker)`). Downgrade drops the table and the two columns.
- Test schema uses create_all; drop `cadence_test` after the model change so it is
  rebuilt.
- Rollback: revert the migration (all existing sessions already behave as stop-loss off);
  the new cron endpoint is inert if the scheduler is not pointed at it.
- Ops: register the new scheduled trigger to call the stop-loss cron endpoint at the
  chosen frequency with the shared cron token.
