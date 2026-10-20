## 1. Fundamentals derivation helper

- [x] 1.1 Add a pure helper (in `backend/src/cadence/ai_portfolio/_helpers.py`, or a small new module imported there) that maps an `AssetFundamentals.document["figures"]` map to a compact fundamentals sub-object: gross/operating/net margin (income figure ÷ revenue), diluted EPS (fall back to basic), and absolute revenue / net income / operating cash flow. Omit any margin whose revenue is zero or missing. Verify with a unit test covering a full-figure asset, zero/missing revenue (margin omitted, no divide-by-zero), and missing income figures.
- [x] 1.2 Extend the helper so an asset with no fundamentals record, a record whose `status != "available"`, or a crypto asset yields an explicit "fundamentals unavailable" marker rather than invented figures. Verify with unit tests for each unavailable case.

## 2. Opt-in flag: column and migration

- [x] 2.1 Add a non-nullable `use_fundamentals: Mapped[bool]` column (`default=False`, `server_default="false"`) to the `PaperTradingSession` model in `backend/src/cadence/paper_trading/models.py`, mirroring `learning_feedback_enabled`.
- [x] 2.2 Add an Alembic migration (copy the `e1f2a3b4c5d6` learning-feedback column pattern) that adds `paper_trading_sessions.use_fundamentals` as a non-nullable boolean with `server_default=sa.false()` (implicit backfill of existing rows to false); `downgrade` drops the column. Set `down_revision` to the current migration head. Verify the migration round-trips (`alembic upgrade head` → `downgrade -1` → `upgrade head`) cleanly against the test DB.

## 3. Opt-in flag: params, service, and API plumbing

- [x] 3.1 Add `use_fundamentals: bool = False` to `AIBuildParams` (`backend/src/cadence/ai_portfolio/params.py`), include it in `to_payload`, and read it in `from_payload` as `bool(payload.get("use_fundamentals", False))`. Verify with a params round-trip unit test.
- [x] 3.2 Thread `use_fundamentals` into `paper_service.create_session(...)` (`backend/src/cadence/paper_trading/service.py`) — add the parameter and store it on the new session row. Pass it from `flows/build.py` at session creation. Verify a built session persists the flag.
- [x] 3.3 Add `use_fundamentals: bool = Field(default=False, ...)` to `AIPortfolioBuildRequest` and `use_fundamentals: bool` to `PaperTradingSessionRead` (`backend/src/cadence/api/schemas.py`, `from_attributes=True`). Add the request→params mapping in `backend/src/cadence/api/routers/ai_portfolio.py` (the hand-written `AIBuildParams(...)` construction). Verify the flag flows request → params and session → read.

## 4. Version gate and eager loading

- [x] 4.1 Add `FUNDAMENTALS_PROMPT_VERSION = 4` to `backend/src/cadence/ai_portfolio/constants.py`. Verify by import and by a unit assertion that it is greater than `TREND_PROMPT_VERSION`.
- [x] 4.2 Add `selectinload(Asset.fundamentals)` to the universe query in `assets/service.py::list_assets` (used by build and rebalance). Verify with a service test (or query-count assertion) that reading `asset.fundamentals` across the returned assets issues no additional per-asset query.

## 5. Attach fundamentals to candidates and holdings

- [x] 5.1 In `_candidates_from_universe` (`_helpers.py`), attach a `"fundamentals"` key (from the task 1 helper) to each candidate dict only when the gate holds — `use_fundamentals AND version >= FUNDAMENTALS_PROMPT_VERSION`; thread the opt-in + version gate from `flows/build.py` (active prompt version) and `flows/rebalance.py` (session's frozen `rebalance_prompt_version`), mirroring the trend gate. Verify with a unit test: present for an opted-in v4 candidate set, absent for an opted-out v4 set and for a v3 set.
- [x] 5.2 In `_build_holdings`, attach the same `"fundamentals"` key to each holding dict under the same gate. Verify with a unit test: present for opted-in v4 holdings, absent for opted-out v4 holdings and v3 holdings.

## 6. Seed rebalance prompt v4

- [x] 6.1 Add an Alembic migration (copy the `a7b8c9d0e1f2_seed_rebalance_prompt_v3.py` pattern) that seeds REBALANCE `version = 4`: `_V4_INSTRUCTIONS` documenting the per-ticker `fundamentals` object **defensively** (weigh it when present; it may be absent for an opted-out session or an asset without usable data), preserving long-only / ~1.0 weights / transaction-cost / discovery-cap framing, and `_V4_INPUT_TEMPLATE` equal to the v3 template verbatim. Set `down_revision` to the column migration (task 2.2) or current head; `downgrade` deletes the v4 row. Verify the migration round-trips cleanly against the test DB.
- [x] 6.2 Confirm `get_active_rebalance_prompt` now returns version 4 for the REBALANCE kind after upgrade, and that a build freezes `rebalance_prompt_version = 4`. Verify with a flow/service test.

## 7. Frontend opt-in toggle and fact tile

- [x] 7.1 Add a company-fundamentals opt-in toggle (default off) to `frontend/src/pages/portfolios/BuildAIPortfolioCard.tsx`, and include `use_fundamentals` in the `build.mutate` payload. Add the field to the build-request and session-read types in `frontend/src/types/api.ts`. Verify with a vitest covering default-off and sending the flag when toggled on.
- [x] 7.2 Add a "Company fundamentals" fact tile (`<dt>/<dd>`) to the session-detail `<dl>` in `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`, next to the learning-feedback / risk-guardrails tiles, showing enabled/disabled. Verify with a vitest.

## 8. Integration tests

- [x] 8.1 Add a flow/agent test (injecting a fake `AIPortfolioAgent`) asserting the `fundamentals` key reaches `.rebalance()` in the candidates/holdings for an opted-in session frozen on v4, and is absent for an opted-out v4 session and a v3 session. Reuse `test_ai_portfolio_agent.py` and `test_fundamentals_service.py` fixture patterns.
- [x] 8.2 Add a byte-for-byte seed-equivalence test for the v4 template rendered via `agent._render(...)` (load the migration via `importlib`, following the existing v3 seed-equivalence test), pinning the v4 instructions/template text.

## 9. Verification gates

- [x] 9.1 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` and confirm all pass.
- [x] 9.2 Run `cd frontend && npm run typecheck && npm run test && npm run build` and confirm all pass.
- [x] 9.3 Run `openspec validate --strict add-fundamentals-rebalance-prompt` and confirm the change is valid.
