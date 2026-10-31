## 1. Age formatter

- [x] 1.1 Add a `formatAge(from: string | Date, now?: Date)` helper to `frontend/src/lib/format.ts` that returns a compact human-readable duration (largest whole unit: `<1d`/`today` for same-day, then `Nd`, `Nw`, `Nmo`, `Ny`) from the creation time to now. Keep it pure and deterministic (accept an injectable `now` for testability).
- [x] 1.2 Add Vitest cases for `formatAge` covering same-day, days, weeks, months, years, and boundary rollovers (e.g. 7 days → `1w`, ~30 days → `1mo`, ~365 days → `1y`) and verify `cd frontend && npm run test` passes for the format suite.

## 2. Portfolios list row

- [x] 2.1 Add a portfolio age cell/column to each row in `frontend/src/pages/paper-trading/PaperTradingPage.tsx`, rendering `formatAge(session.created_at)` with the exact creation date as the element's `title` (hover) attribute. Verify by running the dev server (or component test) that each row shows the age alongside the existing columns.
- [x] 2.2 Add/extend the co-located Vitest coverage for the Portfolios list to assert each row renders the age string and exposes the exact creation date on hover, and verify `cd frontend && npm run test` passes.

## 3. Verification

- [x] 3.1 Run `cd frontend && npm run typecheck && npm run test && npm run build` and confirm all are green.
- [x] 3.2 Run `openspec validate show-portfolio-age-on-paper-trading-page --strict` and confirm the change validates.
