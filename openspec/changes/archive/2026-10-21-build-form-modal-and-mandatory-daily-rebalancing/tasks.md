## 1. Backend — daily rebalancing always enrolled

- [x] 1.1 In `ai_portfolio/flows/build.py`, set `schedule_mode = ScheduleMode.DAILY_REBALANCING` unconditionally (remove the `if params.daily_rebalancing else ScheduleMode.MANUAL` branch).
- [x] 1.2 In `ai_portfolio/params.py`, remove the `daily_rebalancing` field from `AIBuildParams`, its entry in `to_payload`, and its line in `from_payload` (unknown keys in historical payloads are ignored — do not re-add a default read).
- [x] 1.3 In `api/schemas.py`, remove the `daily_rebalancing` field from `AIPortfolioBuildRequest`.
- [x] 1.4 In `api/routers/ai_portfolio.py`, remove `daily_rebalancing=payload.daily_rebalancing` from the `AIBuildParams(...)` construction.

## 2. Frontend — remove the opt-in, two-column layout, modal

- [x] 2.1 In `pages/portfolios/BuildAIPortfolioCard.tsx`, remove the `dailyRebalancing` state (`useState`) and the entire "Enroll in daily rebalancing" checkbox block; drop `daily_rebalancing` from the `build.mutate(...)` body. Replace the removed control with a short static note that every AI portfolio rebalances daily.
- [x] 2.2 In `types/api.ts`, remove `daily_rebalancing` from the `AIPortfolioBuildRequest` type.
- [x] 2.3 In `BuildAIPortfolioCard.tsx`, make the advanced/risk-control grid a consistent two-column layout: remove `sm:col-span-2` from the risk-guardrails card so each toggle card occupies one grid cell, and simplify the guardrails' nested four-field parameter grid to a single column so it reads cleanly in the narrower card. Update the explanatory comment about the layout accordingly.
- [x] 2.4 Add `frontend/src/components/Modal.tsx`: a reusable accessible modal — centered dialog over a backdrop, `role="dialog"`, `aria-modal="true"`, an accessible label (title), a close (×) control, close on backdrop click, and close on Escape (keydown while open); props `{ open, onClose, title, children }`. Render nothing when `open` is false. Focus the dialog on open.
- [x] 2.5 In `pages/paper-trading/PaperTradingPage.tsx`, stop rendering `<BuildAIPortfolioCard />` inline; add a primary "Build an AI portfolio" button where it sat, hold `buildOpen` state, and render the form inside `<Modal open={buildOpen} onClose={...}>`. Adjust the card's outer wrapper (drop `h-full`) so it sits naturally in the modal body; keep the card's running/terminal rendering and its terminal query-invalidation intact so the lists behind the modal still refresh on completion.

## 3. Backend — tests

- [x] 3.1 In `tests/test_ai_portfolio_service.py`: update the `_params` helper to drop the `daily_rebalancing` kwarg and remove `daily_rebalancing=...` from every call site. Update the two tests (~L889-913) that asserted `daily_rebalancing=False → schedule_mode == MANUAL` so they build without the field and assert `schedule_mode == ScheduleMode.DAILY_REBALANCING`. Ensure at least one test asserts a build enrolls the session in daily rebalancing.
- [x] 3.2 In `tests/test_ai_portfolio_api.py`: remove `daily_rebalancing` from the build-request payload bodies; the build still succeeds and the created session is enrolled in daily rebalancing.

## 4. Frontend — tests

- [x] 4.1 In `pages/portfolios/BuildAIPortfolioCard.test.tsx`: remove assertions about the daily-rebalancing control; add a test that the form renders no daily-rebalancing control and that a submitted build request carries no `daily_rebalancing` key.
- [x] 4.2 Add a test for `components/Modal.tsx`: it renders children only when `open`; it calls `onClose` on the close control, on a backdrop click, and on Escape; it exposes `role="dialog"` / `aria-modal`.
- [x] 4.3 In `pages/paper-trading/PaperTradingPage.test.tsx` (or a focused test): the build form is not shown until the "Build an AI portfolio" button is activated, after which the form appears in the dialog; dismissing it hides the form.

## 5. Verify

- [x] 5.1 Backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 5.2 Frontend gates: `cd frontend && npm run -s typecheck && npx vitest run && npm run build`.
- [x] 5.3 `openspec validate build-form-modal-and-mandatory-daily-rebalancing --strict` passes.
