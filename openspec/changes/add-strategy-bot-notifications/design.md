## Context

See proposal.md — Why. The AI paper-trading subsystem already notifies via a `Notifier`
(Pushover in prod, a null no-op when unconfigured) threaded through its snapshot and
event flows; `ai_portfolio/snapshots.py::snapshot_all_sessions` sends **one push per
session** (no cross-session roll-up) built by `ai_portfolio/notifications.py`
(`_session_snapshot_message` + `_best_worst_line` + `_benchmark_suffix`), all wrapped in
a best-effort `_notify_safely`. The strategy-bots subsystem has **no notifier wired in
at all**: `strategy_bots/service.py::run_tick`/`_tick_session` silently liquidate+stop a
session on a drawdown trip, and `run_bot_snapshots` only writes `BotValueSnapshot` rows
and returns a count. The `POST /api/v1/bots/tick` and `POST /api/v1/bots/snapshot-daily`
routes take no notifier dependency.

Relevant existing data (no migration needed to supply the AI figures):
- `BotKpis` already carries current_value, allocated_capital, total_return,
  total_return_pct, realised_pnl, unrealised_pnl, total_fees, total_trades (lifetime),
  max_drawdown.
- `BotSession` has `cash`, `benchmark`, a label/strategy_key for the title, and
  `peak_value`.
- `BotValueSnapshot` stores total_value/realised_pnl/unrealised_pnl per (session, date)
  but **no** stored daily_pnl/daily_pnl_pct (unlike the AI `SessionValueSnapshot`).
- `BotTrade` has `created_at`, `status`, `fees`, `side`, `ticker`, `quantity`,
  `filled_price`, `reason`.
- `paper_trading.service.sharpe_ratio(returns, *, risk_free)` is a pure helper
  (needs ≥ `SHARPE_MIN_RETURNS` observations, annualises by √`SHARPE_TRADING_DAYS_PER_YEAR`,
  returns `None` otherwise) that can be reused on a bot's own daily-return series.

## Goals / Non-Goals

**Goals:**
- Fire a best-effort Pushover notification from the tick path when the drawdown
  kill-switch liquidates and stops a bot.
- Send a best-effort per-bot evening summary from the snapshot path mirroring the AI
  daily report figures plus the day's trade count.
- Supply the two figures bots don't store directly — daily P&L and Sharpe — by computing
  them from the session's existing snapshot series, with no schema change.
- Expose Sharpe on the bot's own KPIs and detail page too, so the evening notification
  never shows a figure that is absent from the bot's own page.
- Mirror the AI best-effort convention exactly: absent/failed notifier never fails the
  job; unconfigured channel = silent.

**Non-Goals (design-level):**
- No new notification channel, no change to the AI notifications, no change to tick or
  snapshot schedules or market-hours gating.
- No stored daily-P&L columns on `BotValueSnapshot` (compute on the fly).
- No per-trade/entry/exit push — only the kill-switch event and the evening summary.
- No frontend change beyond the bot detail page's Sharpe KPI tile.

## Decisions

**1. A dedicated `strategy_bots/notifications.py` module, paralleling
`ai_portfolio/notifications.py`.** It holds the message builders
(`_kill_switch_message`, `_bot_summary_message`, reusing `_signed_money`/`_signed_pct`
/`_best_worst_line`-style formatting) and a best-effort send guard mirroring
`_notify_safely`. Keeping message construction pure and separate keeps it unit-testable
and keeps `service.py` focused on orchestration. Alternative — inline the strings in
`service.py` — rejected: it couples formatting to DB/orchestration and is harder to test.

**2. Thread `Notifier` as an explicit parameter, not a module global.**
`run_tick(session, *, broker, market_data, now=None, notifier=None)` passes it to
`_tick_session`, which calls the kill-switch send at the point it sets
`status = STOPPED`. `run_bot_snapshots(session, *, broker, notifier=None)` sends one
summary per session it snapshots. Default `None` = silent no-op, so existing callers and
tests that don't pass a notifier keep working unchanged. The routes supply the real
notifier via the existing `NotifierDep`/`get_notifier` factory (already returns a null
no-op when Pushover is unconfigured). Matches the AI subsystem's signature style.

**3. Compute daily P&L by diffing the prior snapshot, exactly like the AI job.** For the
"value today (±$, ±%)" line, read the session's previous `BotValueSnapshot` before the
snapshot date (new helper, e.g. `get_previous_bot_value_snapshot`); daily P&L =
`total_value − prior.total_value`; baseline for the percent is the prior total_value
(fall back to allocated_capital on day one), guarding division by a non-positive
baseline (→ no percent), mirroring `ai_portfolio/snapshots.py::_daily_change_holdings`
and `_session_snapshot_message`.

**4. Count "trades today" with a dedicated query, distinct from lifetime
`total_trades`.** New service helper (e.g. `count_bot_trades_on(session, bot, day)`)
counting `BotTrade` rows for the session whose `created_at` falls on the snapshot date
(in the snapshot/close timezone, consistent with how the snapshot date is derived).
Lifetime `total_trades` from `BotKpis` stays as-is for the other figures; the summary
adds a separate "Trades today: N" line.

**5. Compute a bot Sharpe once in `bot_session_kpis`, exposed on the KPIs and the detail
page as well as the notification.** `bot_session_kpis(session, bot)` is already a pure
function over the session's snapshot series, so Sharpe is computed there: build the daily
fractional-return series from consecutive `BotValueSnapshot.total_value` diffs (bots have
no mid-life capital-increase events, so total-value diffs are clean returns) and call
`paper_trading.service.sharpe_ratio`, which returns `None` until there are enough
observations. Add `sharpe_ratio: float | None` to the `BotKpis` dataclass and the
`BotKpisRead` schema; the evening summary and the detail page both read the one KPI value,
so they can never disagree. The bot detail page (`BotSessionPage.tsx`) renders a Sharpe
tile with a "not yet available" state mirroring the AI session page's Sharpe tile; this is
the only frontend change. Alternative — compute Sharpe privately inside the notification
builder — rejected: it would show a Sharpe in the push that the bot's own page lacks
(the inconsistency this change exists to avoid).

**6. Benchmark comparison is a simple buy-and-hold-vs-total-return line.** Bots already
have a `benchmark`; since bots have no capital-increase events, a since-inception
buy-and-hold benchmark return compared against the bot's total return is sufficient and
avoids the AI job's contribution-time-weighting machinery. Rendered as the AI
`vs NAME: ±% (excess ±%)` suffix. If a benchmark or its priceable closes are
unavailable, omit the suffix (as the AI job does).

**7. One push per bot, no cross-bot roll-up.** The AI job sends exactly one push per
session and no across-all summary, so bots match: one summary per snapshotted session.

## Risks / Trade-offs

- **A manual `POST /api/v1/bots/tick` can now emit a kill-switch push.** → Acceptable:
  it is the same endpoint cron uses, and a kill-switch is a real terminal event worth
  surfacing however the tick was triggered. Documented in the proposal.
- **Sharpe needs ≥ `SHARPE_MIN_RETURNS` daily snapshots; new bots report no Sharpe for a
  while.** → Mitigation: reuse the shared helper's `None` contract and render it exactly
  as the AI report renders a missing Sharpe — no special-casing, no error.
- **Daily P&L on the first-ever snapshot has no prior.** → Mitigation: fall back to
  allocated_capital as the baseline (same as the AI job), guarding a non-positive
  baseline so the percent is simply omitted.
- **A noisy notifier (one push per active bot each evening) could be chatty.** →
  Accepted: it mirrors the AI subsystem's existing cadence and the user explicitly asked
  for the per-bot evening summary.

## Migration Plan

Additive and backward-compatible: new optional `notifier` parameters default to `None`
(silent), no schema/migration, no API contract change. Deploy is code-only. Rollback is
reverting the code; no data to undo. In environments without Pushover configured, the
null notifier makes both notifications no-ops, so behavior is unchanged there.

## Open Questions

None. Sharpe is **included** and exposed on the bot KPIs + detail page as well as the
notification (Decision 5), so the push never shows a figure the page lacks: bots record a
daily value snapshot, so the daily-return series Sharpe needs is available, and the shared
`sharpe_ratio` helper returns `None` until there are enough observations — rendered exactly
like the AI page's/report's not-yet-available Sharpe, matching a brand-new AI portfolio.
The kill-switch push fires on any tick (manual ticks are not expected in practice, and
surfacing a terminal kill-switch event on a manual tick is acceptable).
