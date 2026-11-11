# Tasks

> Build AFTER `add-news-sentiment-rebalance` and `add-price-ml-rebalance` have shipped, and
> sequentially (never in parallel) — this change takes the next free rebalance prompt
> version after the last of them. See proposal "Sequencing".

## 1. Seed the reconciliation-aware rebalance prompt version

- [x] 1.1 Add a seed migration that appends a new rebalance prompt version whose **instructions** = the then-current head version's instructions verbatim + a new **signal-reconciliation** section, and whose **input template** is byte-identical to the head version's template.
- [x] 1.2 Write the reconciliation section defensively: all attached signals are advisory inputs to judgement; convergence strengthens the case; conflicts must be resolved in reasoning and surfaced in the thesis; an "unavailable" marker means absence, not a negative; the section reads correctly with zero, one, or several blocks attached.
- [x] 1.3 Bump the rebalance prompt-version constant (in `ai_portfolio/constants.py`) to the newly seeded value; do NOT change `flows/rebalance.py` signal-attachment logic, any opt-in flag, or the AI output schema.
- [x] 1.4 Confirm the seeded template is byte-identical to the head version's template (only the instructions differ), documented in the migration.

## 2. Soft UI hint on the build form

- [x] 2.1 In `BuildAIPortfolioCard`, derive a boolean from the count of enabled opt-in signal toggles (≥3) and render a soft, non-blocking advisory hint when true.
- [x] 2.2 Ensure the hint never disables the build action, never caps/unchecks/disables a toggle, and never changes the submitted `AIPortfolioBuildRequest`; it hides below the threshold and updates live as toggles change.

## 3. Tests

- [x] 3.1 Backend: assert the newly seeded prompt version's instructions contain the reconciliation section and its template matches the head version's template byte-for-byte; assert the prompt-version constant equals the seeded value.
- [x] 3.2 Backend: assert a session frozen on a pre-reconciliation version renders the rebalance prompt without the reconciliation section (unchanged), and a session frozen on the new version renders it with the section — including when zero/one signal blocks are attached.
- [x] 3.3 Frontend (vitest): the hint appears at ≥3 enabled opt-in signals and is hidden below; toggling updates visibility live; the hint does not disable the build button or alter the submitted request.

## 4. Verify gates

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npm run test && npm run build`.
- [x] 4.3 `openspec validate add-signal-reconciliation-guidance --strict`.
