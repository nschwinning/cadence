## Context

`BuildAIPortfolioCard` (`frontend/src/pages/portfolios/BuildAIPortfolioCard.tsx`) is the AI-portfolio build form. Today it is rendered inline at the top of the Portfolios page (`pages/paper-trading/PaperTradingPage.tsx`), always expanded. It carries an opt-in "Enroll in daily rebalancing" checkbox (`dailyRebalancing` state) whose value is sent as `daily_rebalancing` in the build request. On the backend, `AIPortfolioBuildRequest` (`api/schemas.py`) → `AIBuildParams` (`ai_portfolio/params.py`) → `flows/build.py`, where `schedule_mode = DAILY_REBALANCING if params.daily_rebalancing else MANUAL`.

Three product issues: daily rebalancing is meant to be mandatory but is optional; the advanced toggle grid is not a consistent two-column layout (the guardrails card spans both columns); and the always-inline form clutters the page.

## Goals / Non-Goals

**Goals:**
- Every AI build enrolls its session in daily rebalancing, with no opt-out anywhere in the stack (UI, API, build flow).
- The advanced/risk-control toggle cards read as a clean two-column grid.
- The build form opens in a dismissible modal from a button on the Portfolios page.

**Non-Goals:**
- Changing what daily rebalancing *does* (cron trigger, readiness gate, weekend crypto trigger, notifications — all unchanged).
- Changing any other build option (risk profile, asset scope, benchmark, model, technical indicators, fundamentals, watchlist, stop-loss, guardrail semantics, learning feedback).
- A database migration: the `schedule_mode` column and the `ScheduleMode` enum (including `MANUAL`) are unchanged; only the build path stops producing `MANUAL`.
- Changing the initial-rebalance route or the dead build-agent code.

## Decisions

**Remove the daily-rebalancing opt-in end-to-end rather than hide it.** Leaving a silently-ignored `daily_rebalancing` request field would violate the "no silently-ignored input" principle. So the field is removed from `AIPortfolioBuildRequest`, `AIBuildParams` (field + `to_payload` + `from_payload`), and the router wiring; `flows/build.py` sets `schedule_mode = ScheduleMode.DAILY_REBALANCING` unconditionally. The frontend removes the `dailyRebalancing` state + checkbox and the `daily_rebalancing` key from the submitted body and the TS `AIPortfolioBuildRequest` type.

- *Backward compatibility:* old persisted build-event payloads may still contain a `daily_rebalancing` key; `from_payload` simply ignores unknown keys, so historical events deserialize fine. `MANUAL` stays a valid `schedule_mode` value for any pre-existing manual sessions — only new builds never produce it. No migration needed.
- *Tests:* the two service tests that asserted `daily_rebalancing=False → MANUAL` are updated to assert `DAILY_REBALANCING`; the `_params` helper and its call sites drop the `daily_rebalancing` kwarg; API-test payloads drop the key.

**Two columns as the standard layout.** Remove `sm:col-span-2` from the risk-guardrails card so every advanced toggle card occupies one grid cell within the existing `grid grid-cols-1 items-start gap-4 sm:grid-cols-2`. The guardrails' nested four-field parameter sub-grid is simplified to a single column so it reads cleanly inside the now-narrower card. This is presentation-only and is deliberately *not* encoded as a spec requirement (specs describe behavior, not column counts).

**Build form in a modal via a new reusable component.** No modal/dialog component exists (only an off-canvas `Sidebar` overlay). Add `frontend/src/components/Modal.tsx`: a centered dialog rendered over a backdrop with `role="dialog"`, `aria-modal="true"`, an accessible label, a close (×) control, backdrop-click-to-close, and Escape-to-close (keydown listener while open). It takes `open`, `onClose`, a title, and children. `PaperTradingPage` holds `const [buildOpen, setBuildOpen] = useState(false)`, renders a primary "Build an AI portfolio" button where the card used to sit, and renders `<Modal open={buildOpen} onClose={…}><BuildAIPortfolioCard /></Modal>`.

- The card keeps its existing idle/running/terminal rendering and its `useEffect` that invalidates portfolio/session queries on terminal, so the lists behind the modal still refresh on completion. The card's outer `h-full` wrapper is adjusted so it sits naturally inside the modal (the modal body scrolls if the form is tall).
- The modal stays open until the user dismisses it, so they can watch build progress and see the terminal result; closing is always user-driven.

## Risks / Trade-offs

- **Removing a public request field** is a contract change, but `daily_rebalancing` is only consumed by this app's own frontend; no external client depends on it. Accepting it and ignoring it would be worse (a lie in the schema).
- **Modal accessibility** must not regress keyboard users: the component wires Escape and an explicit close control and focuses the dialog on open. Full focus-trapping is kept minimal (initial focus + Escape) to match the app's existing lightweight overlay patterns; this is acceptable for a single-form modal.
- **A new Modal component** adds surface area, but it is small, reusable, and fills a genuine gap (there is no dialog primitive today).
