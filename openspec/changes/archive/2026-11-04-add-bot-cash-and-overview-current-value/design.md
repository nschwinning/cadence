## Context

See proposal.md — Why. Two read surfaces change:

- Detail KPIs flow `bot_session_kpis` (`strategy_bots/service.py`) → `BotKpis` dataclass → `BotKpisRead` (`api/schemas.py`) → detail page "Performance" tiles. `BotKpis` already carries `current_value` but no cash figure. The session object already has `bot.cash` (live free cash); the detail page shows it as a "Cash" Fact but not as a KPI tile.
- The session list flows `list_bot_sessions` (`api/routers/bots.py`) → `BotSessionRead.model_validate(row)` per row → `BotsPage.tsx` capital column. The endpoint does a plain validate with no mark-to-market, and `BotSessionRead` has `cash`/`allocated_capital` but no `current_value`. The list hook already refetches every 30s.

`bot_session_kpis` already defines the canonical current value: the latest value snapshot's `total_value` when snapshots exist, else `total_value(bot, {})` (cash + positions at cost).

## Goals / Non-Goals

**Goals:**
- Surface available (free) cash as a per-session KPI the detail page can render as a tile.
- Surface each session's current value on the list read so the overview can show it in place of allocated capital.
- Keep the list endpoint cheap and its current value consistent with the detail KPI.

**Non-Goals:**
- No change to how the detail KPI computes current value (reuse only).
- No spendable-net-of-buffer cash figure — "available cash" is free cash (`bot.cash`).
- No change to tick/snapshot/sizing/value-history/notifications/dashboard adapter.

## Decisions

- **`BotKpis.cash` sourced from `bot.cash`.** Add `cash: float` to the `BotKpis` dataclass and `BotKpisRead`, populated directly from the already-loaded session in `bot_session_kpis`. No extra query. "Available cash" = total free, uninvested cash, matching the existing "Cash" fact's source.
  - *Alternative considered:* spendable cash net of the 2% buffer. Rejected — the buffer only limits entry sizing, not the balance; "available cash" most naturally means the free balance, and surfacing a buffer-adjusted number would be a surprising, harder-to-reconcile figure.

- **List current value is snapshot-based, computed per row in the service, not via a live broker fan-out.** Add a small service helper that returns a session's current value using the same rule as `bot_session_kpis` (latest snapshot `total_value`, else `total_value(bot, {})` cost-basis fallback). `list_bot_sessions` calls it per row and sets `current_value` on each `BotSessionRead`.
  - *Alternative considered:* mark every listed session to market with live broker quotes (as the detail KPI's snapshot already was at capture time). Rejected for the list — a broker fan-out across N sessions on every 30s list refetch is expensive and can fail per-row; the latest daily snapshot is already marked-to-market at capture and is the same basis the dashboard and KPI current value use intraday. Consistency and cost both favour snapshot-based.
  - *Consequence:* between snapshots the list's current value moves only when a new snapshot lands (daily) or, pre-first-snapshot, reflects cost basis — identical to what the detail "Current value" KPI shows, so the two pages agree.

- **Overview column is a replacement.** `BotsPage.tsx` renders `current_value` where it rendered `allocated_capital`; the column header becomes "Current value". Allocated capital remains available on the detail page (KPI tile + Capital fact), so no information is lost overall.

- **Detail "Cash" Fact removed in favour of the new tile.** The Performance-section "Available cash" tile supersedes the redundant "Cash" Fact; drop the Fact to avoid showing the same number twice. (Leaves the "Capital"/"Cash buffer" facts intact.)

## Risks / Trade-offs

- [List current value is as stale as the latest daily snapshot] → Accepted and intended: it matches the detail KPI's own current value exactly (same rule), so the pages never disagree; a live mark would make them diverge and cost a per-row broker fan-out. The 30s list refetch still picks up new snapshots and status changes promptly.
- [Adding a non-optional `current_value` to `BotSessionRead` touches a widely-used schema] → `BotSessionRead` is produced at five router sites via `model_validate(row)` (create/list/get/stop/archive); a plain ORM `model_validate` would leave the new field unset. Resolve by routing all five through one router helper `_to_read(db, row)` that does `model_validate(row)` then sets `current_value` from the new service helper. This keeps the field reliably non-null everywhere (frontend type stays `number`), costs each non-list endpoint one extra cheap snapshot lookup (negligible), and avoids a nullable field the overview would have to guard.
