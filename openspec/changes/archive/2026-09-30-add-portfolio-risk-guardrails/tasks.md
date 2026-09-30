## 1. Config defaults

- [x] 1.1 Add guardrail default constants in `config.py` beside `STOP_LOSS_DEFAULT_PCT` (`GUARDRAIL_DEFAULT_MAX_ASSET_PCT`, `GUARDRAIL_DEFAULT_MAX_ASSET_CLASS_PCT`, `GUARDRAIL_DEFAULT_MIN_POSITIONS`, `GUARDRAIL_DEFAULT_MAX_INVESTED_PCT`) and verify they import and type-check via `uv run mypy src/cadence`

## 2. Schema & migration

- [x] 2.1 Add columns to `paper_trading/models.py` (`risk_guardrails_enabled` non-null default false, `max_asset_class_pct`, `min_positions`, `max_invested_pct` nullable), mirroring the `stop_loss_*` columns, and verify the model imports
- [x] 2.2 Write an Alembic migration (down_revision = current head) adding the four columns and backfilling existing rows to disabled/no-op (`risk_guardrails_enabled=false`, params NULL, `max_allocation_pct` unchanged); verify with `uv run alembic upgrade head` then `downgrade` round-trip and `uv run alembic check` (no drift)

## 3. Deterministic enforcement helper

- [x] 3.1 Implement `enforce_guardrails(weights, asset_classes, caps)` in `ai_portfolio/executor.py`: iterative clamp+redistribute (per-asset then per-class to a bounded fixed point) then max-invested scale, leaving the deficit as cash on infeasible caps; verify new unit tests in `test_ai_portfolio_executor.py` cover per-asset clamp, per-class clamp, the per-asset↔per-class fixed point, max-invested scaling, and the infeasible-cap cash fallback
- [x] 3.2 Call `enforce_guardrails` at the build seam in `execute_build` (after the existing normalize) and the rebalance seam in `execute_rebalance` (after weight normalization), guarded by the enabled flag; verify existing executor tests still pass and the guardrail-on path produces capped target share counts

## 4. Build-time freeze thread

- [x] 4.1 Add guardrail fields to `AIPortfolioBuildRequest` in `api/schemas.py` (enable flag + four params) with a validator defaulting missing params from config when enabled (mirroring `_default_stop_loss_pct`); verify request-validation tests in `test_ai_portfolio_api.py`
- [x] 4.2 Extend `AIBuildParams` dataclass (`ai_portfolio/service.py`) with the guardrail fields and update `to_payload`/`from_payload`; verify a round-trip unit test
- [x] 4.3 Thread the fields through `api/routers/ai_portfolio.py` (`AIBuildParams(...)` construction) and `paper_trading/service.py` `create_session(...)` kwargs → session row; verify a build persists the frozen guardrail config on the session
- [x] 4.4 In `run_build_event`, write the per-asset cap into `max_allocation_pct` (portfolio + session) from params instead of the hardcoded `1.0`, and pass the guardrail caps into `execute_build`; verify a build-with-guardrails service test asserts the frozen columns and capped trades

## 5. Rebalance read-back

- [x] 5.1 In `run_rebalance_event`, read the frozen guardrail config off `session_row` (treating disabled/missing as no caps) and pass the caps into `execute_rebalance`; verify a rebalance service test shows AI weights over the caps are clamped and an opted-out session is unchanged

## 6. Agent prompt + min-positions surfacing

- [x] 6.1 When guardrails are enabled, include the caps (max per asset, max per class, min positions, max invested) in the build and rebalance prompts in `ai_portfolio/agent.py`; verify a prompt-assembly test asserts the caps appear when enabled and are absent when disabled
- [x] 6.2 Record a min-positions guardrail observation in the run's `run_stats` when the AI returns fewer holdings than the configured minimum (no fabrication, no failure); verify a service test asserts the observation is recorded and the build/rebalance still succeeds

## 7. Read model

- [x] 7.1 Add the guardrail config (enabled + four values) to `PaperTradingSessionRead` in `api/schemas.py`; verify a session-read test exposes them and a pre-migration/disabled session reports guardrails off

## 8. Frontend

- [x] 8.1 Mirror the new fields on `PaperTradingSession` and `AIPortfolioBuildRequest` in `frontend/src/types/api.ts`; verify `npm run typecheck`
- [x] 8.2 Add the guardrails toggle + parameter inputs (max per asset, max per class, min positions, max invested) to `pages/portfolios/BuildAIPortfolioCard.tsx`, defaulting off and hiding/disabling the params while off, and send them on the build request; verify build-form vitest covers default-off, enabling with params, and request assembly
- [x] 8.3 Add a guardrail fact tile to `pages/paper-trading/PaperTradingSessionPage.tsx` mirroring the Stop-loss tile (enabled → show the four values; disabled → show disabled); verify session-page vitest covers both states

## 9. Full verification

- [x] 9.1 Run backend `uv run ruff check . && uv run mypy src/cadence && uv run pytest` and frontend `npm run typecheck && npx vitest run && npm run build`; verify all green
- [x] 9.2 Run `openspec validate add-portfolio-risk-guardrails --strict` and verify it passes
