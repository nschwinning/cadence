## 1. Backend

- [x] 1.1 Relax `RollingAverageReversionParams` to allow `exit_threshold == entry_threshold` and `exit_z == entry_z` in revert mode; verify with pytest (equal band and z thresholds accepted; exit above entry still rejected; zero/zero enters strictly below and exits at the average on the next bar; existing reversion tests unchanged).
- [x] 1.2 Add the `rolling_reversion_gradient_algo3` preset; verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: reversion threshold order `exit ≤ entry`, hints updated; verify with vitest (the Algo 3 preset applies 0 / 0 and submits; exit above entry still blocks submit).

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: Gradient Convergence shipped as a Rolling-Average Reversion preset; Tier 2 course ports complete.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-gradient-convergence-preset --strict` passes.
