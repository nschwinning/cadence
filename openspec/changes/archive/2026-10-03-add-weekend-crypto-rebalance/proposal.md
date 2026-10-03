## Why

Crypto trades 24/7, but Cadence's rebalance cron runs Monday–Friday only
(`REBALANCE_SCHEDULE "35 9 * * 1-5"` → `POST /ai-portfolio/rebalance-daily`).
The weekday run already trades crypto even when the equities market is closed, so
the only gap is **Saturday and Sunday**: for two days each week a session's crypto
holdings drift untended. We want a dedicated weekend run that rebalances **only the
crypto sleeve** of each session, leaving equities alone.

Doing that cleanly exposes a latent problem: the rebalance agent today is told
`cash_available = broker.buying_power` — the **global, shared broker's** cash, not
the session's own free cash — and the executor sizes every trade off the session's
full `allocated_capital`. For a crypto-only run of a mixed stocks+crypto session
that is wrong: the agent's crypto weights normalise to ~1.0 and the executor would
try to pour the session's *entire* capital into crypto, ignoring the equities it is
holding. So the weekend run must size crypto against a proper per-session
**crypto budget**, which means the session's real **unallocated (free) cash** has to
be computed and surfaced — to the agent, and (per product decision) to the UI.

## What Changes

- **Weekend crypto-only rebalance trigger.** A new cron-guarded endpoint
  `POST /ai-portfolio/rebalance-crypto-daily` that mirrors the existing daily
  trigger's targeting (active sessions enrolled in daily rebalancing, skip
  already-running, defer sessions whose build orders have not settled) but starts a
  **crypto-only** rebalance job. Sessions that neither hold nor target crypto are
  skipped **without invoking the agent**. A new weekend-only cron schedule
  (default Sat+Sun 09:35 America/New_York) drives it.
- **Crypto-only scoping of the run.** The weekend run intersects the candidate and
  holdings universe with the crypto asset class regardless of the session's own
  asset scope, so a stocks+crypto session rebalances only its crypto; equities are
  left untouched (never sold).
- **Crypto-budget sizing ("unallocated capital").** On a crypto-only run, crypto
  target weights are sized against the session's **crypto investable budget =
  current crypto positions' market value + the session's unallocated cash**, not the
  full `allocated_capital`. This lets the run rotate between existing cryptos and
  deploy idle cash into crypto while never touching equity capital.
- **Session-accurate cash to the agent.** The rebalance agent's account summary
  carries the session's own derived unallocated cash (and, for the crypto-only run,
  the crypto investable budget) instead of the shared broker's global buying power,
  so it reasons with the session's real free capital.
- **Crypto-scoped rebalance prompt.** The crypto-only run uses a dedicated seeded
  rebalance-prompt version whose instructions make clear it is rebalancing only the
  crypto sleeve within the given crypto budget and must not expect equities to trade.
- **Unallocated capital in the KPIs and UI.** The live session KPI summary gains the
  session's unallocated cash (already computed internally for valuation), and the
  session detail view shows it as a KPI tile.

## Capabilities

### New Capabilities

_None._ This change extends existing capabilities.

### Modified Capabilities

- `daily-rebalancing`: add a cron-guarded **weekend crypto-only** rebalance trigger
  alongside the existing daily trigger (same token guard, readiness deferral, and
  already-running skip), scoped to crypto and skipping sessions with no crypto
  without running the agent.
- `ai-paper-trading`: add crypto-only rebalance **scoping** (equities untouched) and
  **crypto-budget sizing** against crypto value + unallocated cash; feed the
  session's own **unallocated cash** (and the crypto budget) to the rebalance agent's
  account summary; use a **crypto-scoped rebalance prompt** version for the
  crypto-only run; and expose the session's **unallocated cash** in the live KPI
  summary.
- `app-shell`: add an **unallocated-cash** tile to the session performance KPI tiles.

## Impact

- **Backend code**: `api/routers/ai_portfolio.py` (new endpoint + response counts);
  `ai_portfolio/service.py` (crypto-only run path: crypto scoping, crypto-budget
  computation from `compute_session_value().cash_value`, account-summary cash,
  crypto prompt selection); `ai_portfolio/executor.py` (crypto sizing uses the
  crypto budget as base capital for this run); `ai_portfolio/agent.py` /
  `account_summary` construction; `paper_trading/service.py` (`session_kpis` exposes
  unallocated cash — figure already computed in `compute_session_value`);
  `api/schemas.py` (`PaperTradingSessionKpisRead` gains an unallocated-cash field).
- **Migrations (Alembic)**: a new seeded `RebalancePrompt` version row for the
  crypto-scoped prompt (pattern of the existing v3 seed migration). Whether sessions
  need a frozen crypto-prompt-version column vs. resolving it at run time is a
  design decision.
- **Deploy/config**: `docker-compose.yml` (new `crypto` cron schedule +
  `crypto-rebalance.sh` sending the `X-Cron-Token`), `.env.example`, `README.md`,
  and `scripts/` (a manual-trigger helper mirroring `run-rebalance.sh`).
- **Frontend**: `types/api.ts` + the paper-trading KPI client and session detail
  view (new unallocated-cash tile).
- **No change** to the order model (still market/day); no change to the weekday run.
