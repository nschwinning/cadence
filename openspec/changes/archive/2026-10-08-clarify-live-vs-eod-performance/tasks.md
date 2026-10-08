## 1. Live indicator on the performance KPI tiles

- [x] 1.1 In `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`, add a "Live" indicator beside the performance KPI tiles section heading, styled with existing Tailwind/badge patterns on the page, with a brief hint (title/tooltip or helper text) that the tiles reflect current broker quotes and can differ from the end-of-day chart intraday. Verify by rendering the session page in a Vitest test and asserting the live indicator text and its hint are present in the KPI tiles section.

## 2. End-of-day indicator on the value chart

- [x] 2.1 In `frontend/src/pages/paper-trading/SessionValueChart.tsx`, add an "End of day" indicator beside the chart heading, styled consistently with the page, with a brief hint that the chart shows end-of-day snapshots (latest point = prior close) and can lag the live tiles intraday. Verify by rendering the chart in a Vitest test with sufficient history and asserting the end-of-day indicator text and its hint are present. Confirm the indicator still renders (or is handled sensibly) in the not-enough-history/placeholder state.

## 3. Verification

- [x] 3.1 Confirm no backend/service/schema/API/migration files changed (presentation-only): `git status` shows changes only under `frontend/`. 
- [x] 3.2 Run the frontend gate green: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 3.3 Run `openspec validate clarify-live-vs-eod-performance --strict` and resolve any issues.
