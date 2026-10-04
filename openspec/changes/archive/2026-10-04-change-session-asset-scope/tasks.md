## 1. Backend — surface scope on the session read model

- [x] 1.1 Add `asset_types: str` (default `AssetScope.BOTH.value`) to `PaperTradingSessionRead` in `api/schemas.py`, populated from `session_metadata["asset_types"]` (model validator or router-side population), mirroring the build-request `asset_types` field + its validator; verify a unit/API test shows a legacy session (no `asset_types` key) reads as `"both"` and a scoped session reads its stored value.

## 2. Backend — change-scope service + endpoint

- [x] 2.1 Add an invalid-scope domain error (or reuse an existing one) in `paper_trading/errors.py` for a scope outside the supported set; verify it carries the allowed scopes in its message.
- [x] 2.2 Implement `change_session_scope(session, session_id, scope, broker)` in `paper_trading/service.py`: validate via `AssetScope(scope)` (raise the invalid-scope error on failure), `get_session` (raise not-found), short-circuit as a no-op when the scope is unchanged, otherwise reassign `session_metadata` with the new `asset_types`, commit + refresh, return the row; verify unit tests for persisted scope, unknown-session error, invalid-scope error, and unchanged-scope no-op.
- [x] 2.3 Implement narrowing liquidation inside `change_session_scope`: compute `scope_categories(new_scope)`, resolve each open position's `AssetClass`/`AssetCategory` via the universe class map, and for each out-of-scope position submit a broker sell, record the trade with `TRANSACTION_COST_USD` into `total_fees`, close the position in the ledger, and recompute+record the session value; verify a unit test (StubBroker) that narrowing `both`→`stocks` sells held crypto, charges fees, closes the crypto position, and leaves equities untouched.
- [x] 2.4 Verify (unit test) that widening scope and a no-op scope change make no broker calls and sell nothing.
- [x] 2.5 Add `PUT /paper-trading/sessions/{session_id}/scope` in `api/routers/paper_trading.py` with a request body model (e.g. `SessionScopeChangeRequest`), `Depends(get_broker)`, returning `PaperTradingSessionRead`; map `SessionNotFoundError`→404, invalid-scope→422, broker `ConnectionError`→503; verify API tests cover success (200 + updated scope), 404, 422, and 503.

## 3. Frontend — type, client, and UI

- [x] 3.1 Add `asset_types: 'stocks' | 'crypto' | 'both'` to the `PaperTradingSession` interface in `types/api.ts` (reuse the existing union); verify `npm run typecheck` passes.
- [x] 3.2 Add `changeSessionScope` raw fn + `useChangeSessionScope` mutation hook in `api/paperTrading.ts` (invalidate `paperTradingKeys.all` + kpis + valueHistory on success), mirroring the benchmark change; verify the co-located client test asserts the PUT URL/body and that invalidation keys match the benchmark hook's.
- [x] 3.3 Render a read-only scope fact tile and a `ScopeSwitcher` control in `pages/paper-trading/PaperTradingSessionPage.tsx` (mirror the risk-guardrails tile and `BenchmarkSwitcher`, with pending/error feedback, current scope preselected); verify a component test shows the current scope and that changing it to a non-liquidating scope calls the mutation.
- [x] 3.4 In `ScopeSwitcher`, when the selected scope would liquidate currently-held positions (a narrowing that excludes a held position's asset class, determined from the session's open positions + their asset class), show a confirmation warning that holdings will be sold and only call the mutation after explicit confirmation; declining leaves the displayed scope unchanged and calls nothing; verify component tests for (a) a liquidating narrowing prompts and only mutates on confirm, (b) declining mutates nothing and keeps the current scope, (c) a non-liquidating change mutates without a warning.

## 4. Verification

- [x] 4.1 Backend: run `uv run ruff check . && uv run mypy src/cadence && uv run pytest` from `backend/` and confirm all green.
- [x] 4.2 Frontend: run `npm run typecheck && npx vitest run && npm run build` from `frontend/` and confirm all green.
- [x] 4.3 Run `openspec validate change-session-asset-scope --strict` and confirm it passes.
