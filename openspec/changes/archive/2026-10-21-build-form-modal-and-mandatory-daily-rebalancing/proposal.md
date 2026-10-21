## Why

The AI portfolio build form (`BuildAIPortfolioCard`) has three rough edges on the Portfolios page:

1. **Daily rebalancing is still an opt-in checkbox**, even though every AI portfolio is meant to rebalance daily — that is the product's whole operating model. Leaving it optional lets a user build a portfolio that silently never rebalances, contradicting the intent.
2. **The advanced/risk-control toggles do not lay out as a consistent two-column grid.** The risk-guardrails card spans both columns and the learning-feedback card sits alone, so the last two options break the two-column rhythm the rest of the form follows.
3. **The build form is rendered inline as a large always-expanded card at the top of the Portfolios page**, pushing the actual portfolio/session content down and cluttering the page even when the user is not building anything.

## What Changes

- **Daily rebalancing becomes mandatory.** The build no longer accepts a daily-rebalancing opt-in: every built session is always enrolled in daily rebalancing. The `daily_rebalancing` request field is removed from the build API (it is not left as a silently-ignored input), and the build flow always sets the session's schedule mode to daily rebalancing. The build form drops the "Enroll in daily rebalancing" checkbox and instead shows a short note that every AI portfolio rebalances daily. (The per-session enrollment record and the `MANUAL` schedule mode remain valid for pre-existing sessions; only the build path no longer produces a manual session.)
- **Two columns become the standard layout** for the advanced/risk-control toggle cards: the risk-guardrails card no longer spans both columns, so every toggle card occupies a single grid cell and the grid reads as a clean two-column layout. This is a presentation refinement only.
- **The build form moves into a modal.** The Portfolios page shows a "Build an AI portfolio" trigger button; clicking it opens the build form in an accessible modal dialog. The modal is dismissible via an explicit close control, a backdrop click, and the Escape key. The form's running and terminal states render inside the modal, and the sessions/portfolios lists behind it still refresh when a build completes. A new reusable modal component is added (none exists today).

## Capabilities

### Modified Capabilities
- `ai-paper-trading`: "Build an AI portfolio and execute it as paper trades" — the request no longer accepts a daily-rebalancing option; a built session is always enrolled in daily rebalancing.
- `daily-rebalancing`: "Enrollment in daily rebalancing" — every build enrolls the resulting session (enrollment no longer depends on daily rebalancing being requested).
- `app-shell`: "AI build form asset scope and default capital" — the build form is opened from a control on the Portfolios page and presented in a modal dialog, and offers no daily-rebalancing enrollment choice.

## Impact

- **Backend:** `ai_portfolio/flows/build.py` (always enroll), `ai_portfolio/params.py` (drop `daily_rebalancing`), `api/schemas.py` (drop the request field), `api/routers/ai_portfolio.py` (drop the wiring). Backend tests in `test_ai_portfolio_service.py` and `test_ai_portfolio_api.py` updated.
- **Frontend:** `pages/portfolios/BuildAIPortfolioCard.tsx` (remove the control + state, two-column grid, modal-friendly content), `types/api.ts` (drop the field), `pages/paper-trading/PaperTradingPage.tsx` (trigger button + modal), a new `components/Modal.tsx`, plus component tests.
- **No migration**, no schema/DB change (the `schedule_mode` column and `ScheduleMode` enum are unchanged), and no change to what daily rebalancing does (cron trigger, readiness gate, weekend crypto trigger all unchanged).
