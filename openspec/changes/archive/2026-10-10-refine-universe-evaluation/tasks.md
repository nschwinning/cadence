## 1. Scope-aware evaluation prompt (backend, `assets`)

- [x] 1.1 In `backend/src/cadence/assets/universe_agent.py`, update the `_AGENT_INSTRUCTIONS` system prompt to state Cadence's scope — universe may only hold US Alpaca-tradable individual equities and crypto, managed long-only with full-universe weighting (no shorting/leverage/options/derivatives), and cannot hold ETFs, mutual/bond/money-market funds, fixed-income, cash-equivalents, or foreign (non-US-listed) securities — and that suggestions must stay in-scope and never recommend unsupported instrument classes; keep the agent otherwise identical (tool-less, structured `UniverseEvaluationOutput`, no numeric scores, single-sentence bullets). Verify by reading back the constant.
- [x] 1.2 In the same file, update `build_universe_evaluation_prompt(summary)` so the per-summary input repeats the in-scope constraint and directs suggestions to in-scope actions (add specific stocks/crypto, reduce concentration, address gaps, resolve foreign/unpriceable listings to US listing/ADR); keep the builder pure/deterministic. Verify the function still takes only `UniverseSummary` and returns a string.
- [x] 1.3 Extend the existing `build_universe_evaluation_prompt` unit test(s) in the assets test suite to assert the in-scope constraint language is present (stocks + crypto only, long-only, no ETFs/funds/fixed-income). Verify with `cd backend && uv run pytest` for the affected test module.

## 2. Collapsible evaluation panel (frontend, `app-shell`)

- [x] 2.1 In `frontend/src/pages/assets/UniverseEvaluationPanel.tsx`, add local `useState` collapse state (default expanded) and a header disclosure toggle button with `aria-expanded`/`aria-controls` that shows/hides the panel body (EvaluationBody + "Generated …" timestamp and the generating/error/empty/outdated states), keeping the header title/subtitle/Refresh visible and functional when collapsed. Verify the panel renders expanded by default in the app.
- [x] 2.2 Add/extend the co-located `UniverseEvaluationPanel` vitest to assert the body is visible by default, hidden after toggling collapse, shown again after toggling expand, and that `aria-expanded` reflects state. Verify with `cd frontend && npx vitest run` for the affected test file.

## 3. Verification

- [x] 3.1 Run backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green.
- [x] 3.2 Run frontend gates: `cd frontend && npm run typecheck && npx vitest run && npm run build` — all green.
