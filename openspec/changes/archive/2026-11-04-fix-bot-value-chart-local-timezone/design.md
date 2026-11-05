## Context

See proposal.md — Why. The fix is a frontend label-formatting change in `BotValueChart.tsx`. The one subtlety worth recording is why intraday labels flip to local time but daily/monthly must not.

## Goals / Non-Goals

**Goals:**
- Intraday (`5min`/`hourly`) chart labels render in the viewer's local timezone, matching the trade ledger on the same page.
- Keep the exact label format (field order, zero-padding, separators) — only the timezone basis changes.

**Non-Goals:**
- No change to daily/monthly labels, the `lib/format.ts` daily/monthly helpers, the backend timestamps/stamping, or the endpoint shape.

## Decisions

**Intraday: format from local Date getters, not `.toISOString()`.** Build `dd.MM HH:mm` / `dd.MM.yyyy HH:mm` from the local `Date` components (`getDate`/`getMonth`/`getFullYear`/`getHours`/`getMinutes`, zero-padded) of the point's epoch ms. The epoch value is already correct (`Date.parse(p.timestamp)`); only the label derivation changes. *Alternative considered:* `toLocaleString`/`toLocaleTimeString` with explicit `{ day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false }` — also local, but locale-dependent separators risk drifting from the fixed `dd.MM HH:mm` shape; explicit getters keep the format deterministic and keep the test timezone-agnostic.

**Daily/monthly stay UTC calendar-date.** Daily snapshot points are backend-stamped at `23:59:59 UTC` so a day's end-of-day point sorts after that day's intraday points on the shared timeline. The daily/monthly formatters read the UTC calendar **date** on purpose: for a viewer east of UTC, a `23:59:59Z` instant rendered in local time becomes `00:59:59` the next day, shifting the label one calendar day forward. Those resolutions show only a date (no clock time), so there is no timezone bug to fix there — changing them would introduce the day-shift. *Decision:* leave them and the backend convention untouched.

## Risks / Trade-offs

- [A reviewer might expect daily labels to also "go local" for consistency] → They intentionally do not, to avoid the `23:59:59Z` day-shift; the spec's second scenario and this design record the rationale. The user-visible inconsistency being fixed is only the intraday clock time.
- [Test could be flaky if it hard-codes a CET expectation while CI runs in UTC] → The test computes the expected label from the same `Date` via local getters, so it passes in any CI timezone and still asserts "not the UTC-sliced value" only when local ≠ UTC.
