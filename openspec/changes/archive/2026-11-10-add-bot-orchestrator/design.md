## Context

The building blocks exist:
- AI portfolios already rebalance on a daily, weekly or monthly cadence: the pure
  `ai_portfolio/scheduling.rebalance_due`, anchored on the last succeeded or partial
  event, triggered by the cron at 09:35 ET and guarded by `require_valid_cron_token`.
- The agent framework provides `build_agent` (mandatory Pydantic `output_type`), the
  `web_search` tool with `web_search_budget`/`record_web_searches`, `llm_trace`, and the
  Protocol plus fake seam used for tests.
- Bots can be created from presets (`create_bot_session(preset_key=…)`).

The gaps that shape this design:
- **Stopping doesn't sell.** `stop_bot_session` only flips the status, and `run_tick`
  iterates active sessions only, so a stopped bot's positions are never sold.
- **Creation is hardcoded as manual.** `create_bot_session` has no `origin` parameter and
  always records `manual`.
- **No market-level or sector-level inputs.** News is per-ticker tone only and is not
  persisted (an in-process cache per `(ticker, date)`). Indicators are per asset, latest
  snapshot only. Benchmark indices have stored daily **closes** (`benchmark_prices`) but
  no indicators.
- **One shared Alpaca paper account.** All AI sessions and bots trade it, and capital is a
  per-session ledger, so limits must be enforced from the database.
- **One global AI job worker.** `AIPortfolioJobRunner` is a single-worker executor used by
  every build and rebalance.

## Goals / Non-Goals

**Goals:**
- Stops that end flat for every bot, through one code path.
- An orchestrator whose AI chooses only among presets and eligible tickers, and whose every
  action is validated deterministically against its capital pool and limits.
- Full auditability of each run: inputs, output, what was applied, what was rejected and why.

**Non-Goals:**
- New data providers (sector ETFs, market-news feeds), persisted news, indicator history.
- The AI choosing sizing, editing running bots, or trading crypto.
- Coordinating orchestrator bots with AI portfolios that hold the same symbols on the shared
  account (an existing limitation of the shared account; see Risks).

## Decisions

**1. Separate `bot_orchestrator` package, one-way dependency.** It imports the
`strategy_bots` service (create, stop, current value, KPIs, presets); `strategy_bots` never
imports it. The only coupling in the other direction is the `bot_sessions.orchestrator_id`
column. Folding the orchestrator into `strategy_bots` was rejected because that service is
already ~1,700 lines and the orchestrator has its own lifecycle, runner and agent.

**2. Selling stop = a flatten pass in the intraday tick.**
- `run_tick` gains a pass, run before the active-session pass, over **non-active**
  sessions (stopped or archived) that still hold positions. It marks each position's
  price and sells through the existing `ExecutionEngine.exit` with reason
  "session stopped".
- `stop_bot_session` keeps doing only the status flip, gains a `reason` parameter
  (default manual), and records it.
- This gives one market-hours-safe path for every stop: manual, orchestrator, and legacy
  stopped bots with leftovers. The cost is a ≤5-minute delay while the market is open.
- Rejected: selling inside the HTTP stop call. That needs broker calls in a request
  handler, a second code path for the market-closed case, and still needs the tick pass
  for legacy stopped bots.
- A sell the broker rejects (e.g. the shared account no longer holds the shares) is
  caught per position as `BrokerError` and logged. The position stays on the ledger and
  is retried on the next tick, so one bad leftover cannot abort the tick for every other
  session.
- The bot detail page needs no change: the trade ledger shows the sells, and the
  stopped-session summary's input fingerprint changes, so its narrative regenerates.

**3. Provenance on creation.** `create_bot_session` gains keyword-only
`origin: BotOrigin = MANUAL` and `orchestrator_id: UUID | None = None`. `BotOrigin` gains
`ORCHESTRATOR` and `StopReason` gains `ORCHESTRATOR`. Both are stored as free text, so no
enum migration. `BotSessionRead` adds `orchestrator_id` and `orchestrator_label`, read
through a relationship.

**4. Capital pool.**
- `bot_orchestrators.free_capital` is decremented in the same transaction as the deploy,
  with the orchestrator row locked (`SELECT … FOR UPDATE`).
- Returned capital is settled by `settle_returned_capital(db, orchestrator)`. It finds the
  orchestrator's bots that are non-active, have no open positions and have
  `capital_returned_at IS NULL`; adds their `cash` to `free_capital`; and stamps
  `capital_returned_at`. It is idempotent under the row lock.
- Settlement runs at the start of every decision run, after the stop-orchestrator path,
  and from the bots tick **router** right after `run_tick`. Calling it from the router
  keeps `strategy_bots` unaware of orchestrators.
- Value and allocation reads are computed, not stored:
  - value = free capital + Σ `bot_current_value` over unreturned bots;
  - allocated = Σ `initial_capital` over unreturned bots.
  Reads are therefore correct even before settlement runs.
- The per-bot cap is applied to the orchestrator **value** at decision time
  (`max_bot_share × value`), so it compounds with the pool.

**5. Tables (one migration).**
- `bot_orchestrators`: id, label, status, `capital` (initial pool), `free_capital`,
  `max_parallel_bots`, `max_bot_share`, `max_tickers_per_bot`, `cadence`, `model`,
  `benchmark`, `created_at`, `updated_at`, `stopped_at`, `archived_at`.
- `bot_orchestrator_runs`: id, orchestrator_id (FK), `trigger` (scheduled/manual),
  `status`, `prompt_version`, `model`, `briefing` (JSONB), `decision` (JSONB, the
  `model_dump` of the AI output), `applied` (JSONB), `rejected` (JSONB), `research`
  (JSONB), `error`, `created_at`, `started_at`, `finished_at`, `duration_ms`. A **partial
  unique index** on `(orchestrator_id) WHERE status IN ('queued','running')` enforces at
  most one live run per orchestrator at the database level.
- `bot_sessions`: `orchestrator_id` (nullable FK, `ON DELETE RESTRICT`, indexed) and
  `capital_returned_at` (nullable).

**6. Cadence reuse.** The orchestrator stores a `RebalanceCadence` value. The due check
maps it with `cadence_to_schedule_mode` and calls `rebalance_due(mode, last_counting_run_at,
now)`, where the anchor is the newest run with status succeeded or partial. A manual run
that succeeds therefore also counts, as the spec requires.

**7. Own single-worker runner.** `OrchestratorJobRunner` is a `ThreadPoolExecutor` with
`max_workers=1`, mirroring `TechnicalIndicatorJobRunner`. This keeps orchestrator runs from
queueing behind AI-portfolio rebalances at 09:35. Runs are created as `queued` by the
endpoint, then executed by the runner. Startup fails orphaned queued or running runs, the
same as AI events. Cron trigger `POST /api/v1/bot-orchestrators/run-due` runs at
`0 9 * * 1-5` ET (env `ORCHESTRATOR_SCHEDULE`), **before the open**. A run places no orders:
deploys and stops only change database state, and the intraday tick (already gated on an
open market) does all trading. So a pre-open run lets new bots trade, and stopped bots be
sold, from the opening bell. The inputs are already final by then: indicators computed at
05:00 from the prior close, index closes stored at 16:05 the day before, and overnight
news. Starting at 09:00 leaves room for a slow run (5-minute agent timeout plus the
sentiment fan-out) to finish before 09:30. Rejected: 09:40 after the open, copied from AI
rebalancing, whose runs do place orders.

**7a. Trading-day check.** "Is the market open?" is always false at 09:00, so the skip rule
is "today is a trading day" instead. A new `Broker.is_trading_day(day) -> bool` reads the
Alpaca market calendar (`/v2/calendar?start=day&end=day`), which returns one session for a
trading day and none for weekends and holidays. `day` is today's America/New_York date, and
`StubBroker` returns true. Rejected: deriving it from `/v2/clock`'s `next_open`, which
points to tomorrow after the close and would wrongly skip an after-hours "Run now". If the
calendar request fails, the run is recorded as failed (not skipped), so
it is retried on the next trigger rather than silently treated as a holiday. Manual runs use
the same check, so "Run now" works any time on a trading day (after the close, bots start
the next morning).

**8. Briefing builder** (`briefing.py`, pure functions over loaded rows, unit-testable):
- **Index technicals:** for SP500, NDX and RUT, build daily close series from
  `benchmark_prices` and run `compute_snapshot`. Volume is unavailable for indices, so the
  volume-derived fields (OBV, volume ratio) are dropped from the index entry. Fewer closes
  than needed → `unavailable`.
- **Sector breadth:** group eligible universe equities by `Asset.sector` (null → "unknown").
  From the `technical_indicator` rows report count, gate-pass share, regime-pass share,
  mean RSI-14 and mean `dist_high_52w`, ignoring assets without a snapshot (counted
  separately).
- **Sector news tone:** `resolve_sentiment_annotations(eligible_tickers)`, aggregated per
  sector (mean score of available signals plus counts by tone). When the scorer is
  unconfigured or every ticker is unavailable → `unavailable`.
- **Candidates, presets, running bots, limits:** compact rows as listed in the spec.
  Running-bot rows reuse `bot_current_value` and `bot_session_kpis`.
- The briefing is JSON-serialisable and stored on the run as is. The prompt renders it
  as sections.

**9. Agent.**
- `OrchestratorAgent` Protocol, with `OpenAIOrchestratorAgent` built by
  `build_agent(name="BotOrchestratorAgent", output_type=OrchestratorDecision,
  tools=[web_search], model=orchestrator.model)`.
- Run via `asyncio.wait_for(Runner.run(..., max_turns=settings.BOT_ORCHESTRATOR_MAX_TURNS),
  timeout=settings.BOT_ORCHESTRATOR_TIMEOUT_SECONDS)` inside
  `web_search_budget(settings.BOT_ORCHESTRATOR_MAX_WEB_SEARCHES)` and
  `llm_trace(f"orchestrator-run-{run_id}")`.
- Defaults: 8 turns, 300 s, 4 searches.
- Timeout and SDK errors map to `OrchestratorUnavailableError` (summary-agent pattern),
  so the run fails with a readable message rather than a bare "TimeoutError".
- Output model: `OrchestratorDecision{market_summary: str, stops: list[StopAction{bot_id,
  reason}], deploys: list[DeployAction{preset_key, tickers: list[str], capital: float,
  rationale}]}`.
- The prompt is a code constant with `ORCHESTRATOR_PROMPT_VERSION` recorded on each run. A
  versioned prompt table (as AI portfolios use) is deferred until prompts need editing
  without a deploy.
- The instructions tell the AI to:
  - prefer few changes and avoid churning young bots;
  - diversify presets and sectors;
  - match presets to conditions (trend presets in strong regimes, reversion presets on
    pulled-back names);
  - stay within the stated limits;
  - return no actions when nothing is warranted.

**10. Validate, then apply in one transaction.**
- A pure `validate_decision(decision, state) -> (accepted, rejected)` walks stops then
  deploys against a mutable copy of the limits (free capital, slots). State is the
  orchestrator's active bot ids, eligible tickers, preset keys, value and limits.
- Ticker comparison is case-insensitive and de-duplicated per deploy (duplicates →
  rejected).
- `apply` then calls:
  - `stop_bot_session(reason=ORCHESTRATOR)` for each accepted stop;
  - `create_bot_session(preset_key=…, tickers=…, initial_capital=…,
    benchmark=orchestrator.benchmark, origin=ORCHESTRATOR, orchestrator_id=…)` for each
    accepted deploy;
  then decrements `free_capital`, all in one transaction.
- If `create_bot_session` raises a domain error (e.g. an asset became ineligible since the
  briefing), that deploy moves to `rejected`. An unexpected exception rolls back the whole
  apply and fails the run, so a failed run never half-applies.
- Status rules follow the spec: everything rejected → failed; a mix → partial;
  all applied or none requested → succeeded.

**11. API** (`/api/v1/bot-orchestrators`):
- `GET /` (include_archived), `POST /`, `GET /{id}`, `POST /{id}/stop`,
  `POST /{id}/archive`;
- `POST /{id}/runs` (manual: 202 with the queued run; 409 if not active or a run is live);
- `GET /{id}/runs` (limit/offset, default 10), `GET /runs/{run_id}`;
- `POST /run-due` (cron).

Detail reads include computed value, allocated capital, counts and the bot list. Domain
errors map to 404, 409 and 422, as for bots.

**12. Frontend.**
- `pages/orchestrators/`:
  - `OrchestratorsPage` (list plus a "Deploy orchestrator" modal);
  - `DeployOrchestratorCard` (form with defaults and validation);
  - `OrchestratorDetailPage` (header actions; capital tiles reusing `StatTile`; a bots
    table; a run-history panel using the shared `Panel` with Prev/Next pages and an
    expandable row per run).
- `api/orchestrators.ts` provides query keys and hooks. The detail and runs queries use
  `refetchInterval: 3000` while the latest run is queued or running. Mutations invalidate
  orchestrator keys plus `invalidateBotDependents`.
- Sidebar entry "Orchestrators" after "Bots" with a new icon; routes `/orchestrators` and
  `/orchestrators/:id`.
- Bot detail provenance shows "Deployed by {label}" linking to `/orchestrators/:id` when
  `orchestrator_id` is set.

## Risks / Trade-offs

- [Positions net per symbol on the shared Alpaca account; an orchestrator bot and an AI
  portfolio holding the same ticker share one broker position] → unchanged from today
  (ledgers are the source of truth). Documented, not solved here.
- [The AI churns bots (deploy, stop, redeploy), paying spread repeatedly] → the prompt
  discourages churn and shows days active; a weekly or monthly cadence is offered;
  parallel-bot and per-bot caps bound the blast radius.
- [The sector news tone fans out one Alpaca news call plus scoring per eligible equity
  (~120) per run] → the existing per-day in-process cache serves repeat runs; the step is
  best-effort and degrades to `unavailable`. Watch the run duration in the audit.
- [The flatten pass sells everything held by every stopped bot on the first tick after
  deploy, including legacy stopped bots] → intended per the spec (stopped bots are flat).
  Called out in the proposal as a behaviour change.
- [Token cost of a ~120-row candidate table every run] → compact rows (ticker, sector, a
  few numbers). The per-run cost appears in LiteLLM spend via `llm_trace`.
- [Stopped capital returns only once the bot is flat, so a stop-then-deploy in the same
  run cannot reuse that bot's cash] → by design: the deploy may use only free capital that
  exists at decision time; the slot is freed immediately, the cash at the next run.

- [The app's startup orphan sweeps open sessions through the shared `SessionLocal`,
  which points at the development database, and the test client runs that startup, so
  pytest touched the dev database (and failed on its missing orchestrator table)] →
  the test fixtures now rebind `SessionLocal` to the test engine for the test run, so
  startup sweeps and background runners use `cadence_test`.

## Migration Plan

1. One Alembic revision: create `bot_orchestrators`, create `bot_orchestrator_runs` with
   the partial unique index, and add `bot_sessions.orchestrator_id` (+ index) and
   `capital_returned_at`. All are additive, and existing bots are unaffected (null
   orchestrator).
2. Verify upgrade → downgrade → upgrade on a scratch database, as before; the test database
   is rebuilt by the fixtures.
3. Deploy, then add the `ORCHESTRATOR_SCHEDULE` cron line. Expect the first market-open tick
   to sell any leftover positions of previously stopped bots.
4. Rollback: downgrade drops the new tables and columns; the flatten pass is code-only.
