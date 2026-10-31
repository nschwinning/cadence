## Why

Today every AI-built portfolio is rebalanced once per trading day, with no other choice. Rebalance cadence is a genuine strategy lever — a slower cadence lets winners ride, cuts transaction-cost drag and fill slippage, and leans on the AI's longer-horizon thesis instead of reacting to daily noise. Offering weekly and monthly cadences alongside daily turns "how often do we rebalance?" into an experiment dimension the existing session-comparison chart and KPIs already surface.

## What Changes

- Add two new scheduling modes, **weekly** and **monthly** rebalancing, alongside the existing **daily** mode. A session's cadence is chosen in the Build card and **frozen at build**, consistent with every other per-session option (model, guardrails, fundamentals, technical indicators, benchmark). The Build form presents the cadence as a **required radio group with no pre-selected default** — the user must actively pick exactly one before submitting. At the API/compatibility level daily remains the fallback, so an unspecified request or a legacy session with no persisted cadence is still treated as daily.
- The daily rebalance cron now fans out to daily, weekly, and monthly sessions, but applies a per-session **calendar-boundary due-check**: a daily session is always due (unchanged); a weekly session is due on the first weekday-cron run of a new ISO week; a monthly session on the first weekday-cron run of a new calendar month (boundaries evaluated in the US market timezone). A session that has never rebalanced is due now, so its opening allocation still lands on the next daily tick regardless of cadence. A not-yet-due session is reported with a distinct skip reason.
- The weekend crypto-only cron stays **daily-cadence only**: weekly and monthly sessions are excluded from it. This guarantees a mixed stock+crypto weekly/monthly session rebalances its whole portfolio exactly once per period on a weekday run, rather than tending crypto on, say, Saturday and the rest of the portfolio the following Monday.
- Surface the frozen cadence on the session read model and on a session-detail fact tile, and add a required rebalance-cadence radio group (daily/weekly/monthly, no pre-selected default) to the Build card.
- One small schema migration: the scheduling-mode column was `VARCHAR(17)` (sized to the old longest value `DAILY_REBALANCING`), so it is widened to `VARCHAR(32)` to hold the longer `WEEKLY_REBALANCING` / `MONTHLY_REBALANCING` values; no rows are rewritten. The due-check still adds no column — it derives its "last rebalanced" anchor from existing rebalance-event history.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `daily-rebalancing`: **Enrollment** now records a per-session cadence (daily/weekly/monthly) frozen at build rather than a single mandatory daily mode. The **cron-guarded daily rebalance trigger** now targets daily, weekly, and monthly sessions and applies a calendar-boundary due-check, skipping not-yet-due sessions with a distinct reason. The **cron-guarded weekend crypto-only trigger** is restricted to daily-cadence sessions.
- `ai-paper-trading`: The **AI portfolio build** accepts and freezes a rebalance cadence onto the session. **Reading session data** exposes the frozen cadence.
- `app-shell`: The Build card offers a rebalance-cadence selector (default daily), and the session-detail view shows the frozen cadence.

## Impact

- **Backend**: `paper_trading/constants.py` (`ScheduleMode` gains `WEEKLY_REBALANCING`, `MONTHLY_REBALANCING`); `ai_portfolio/params.py` (`AIBuildParams` gains a cadence field, threaded through `to_payload`/`from_payload`); `ai_portfolio/flows/build.py` (map the chosen cadence to `schedule_mode` instead of hardcoding daily); `api/routers/ai_portfolio.py` (`rebalance_daily` targeting + due-check; `rebalance_crypto_daily` restricted to daily cadence); a new pure, unit-testable due-check helper plus an anchor derived from the latest successful rebalance event; `api/schemas.py` (build request + `PaperTradingSessionRead` cadence field) and the thin router mapping.
- **Frontend**: `pages/portfolios/BuildAIPortfolioCard.tsx` (cadence selector), `api/aiPortfolio.ts` (build request type), `types/api.ts` (session read), and the session-detail fact tile, plus co-located Vitest.
- **One column-widening migration** (`schedule_mode` → `VARCHAR(32)`). No change to the cron schedule/times, the agent/prompt, sizing, guardrails, cash-buffer, redeploy, or readiness-gate logic beyond cron targeting and the due-check.
- **Compatibility**: existing sessions carry daily cadence and are unaffected; the build request's cadence is optional and defaults to daily.
