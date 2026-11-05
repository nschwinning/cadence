## 1. Frontend — local-timezone intraday labels

- [x] 1.1 In `frontend/src/pages/bots/BotValueChart.tsx`, rewrite `formatIntradayAxis(ms)` to build `dd.MM HH:mm` from the local `Date` components of `ms` (zero-padded `getDate`/`getMonth`+1/`getHours`/`getMinutes`) instead of slicing `new Date(ms).toISOString()`. Verify by reading the function back: no `.toISOString()` remains and the format string is unchanged.
- [x] 1.2 In the same file, rewrite `formatIntradayTooltip(ms)` to build `dd.MM.yyyy HH:mm` from the same local `Date` components (adding `getFullYear`). Verify the format is unchanged and `.toISOString()` is gone from the intraday path.
- [x] 1.3 Confirm the daily/monthly path is untouched — the `daily`/`monthly` branch still delegates to `formatAxisTimestamp`/`formatTooltipTimestamp` from `lib/format.ts` (no edits to `lib/format.ts`). Verify by reading the resolution branch in `buildBotValueOption`.

## 2. Frontend tests

- [x] 2.1 In the `BotValueChart` vitest (create or extend `frontend/src/pages/bots/BotValueChart.test.tsx`), add a test for an intraday resolution: for a known `captured_at` instant, assert the axis label equals the local-time `dd.MM HH:mm` and the tooltip equals the local-time `dd.MM.yyyy HH:mm`, computing the expected strings from the same `Date` via local getters (timezone-agnostic), and assert the label is NOT the UTC-sliced value when the local and UTC clock differ. Verify the test passes.
- [x] 2.2 Confirm a daily/monthly label test still asserts a date-only label on the correct calendar day (add one if none exists). Verify it passes.

## 3. Verification

- [x] 3.1 Run frontend gates: `cd frontend && npx vitest run && npx tsc --noEmit` — all green.
- [x] 3.2 Run `openspec validate fix-bot-value-chart-local-timezone --strict` and confirm it reports valid.
