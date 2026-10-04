## Context

See proposal.md — Why. Asset scope is persisted only as the string `session_metadata["asset_types"]` (values `"stocks" | "crypto" | "both"`, default `"both"`), not as a DB column. It is re-read on every build, rebalance, weekend crypto-cron selection (`session_allows_crypto`), and weekend snapshot gate, so persisting a new metadata value is sufficient to change all future scope-dependent behavior — no extra wiring. The codebase already has the exact analog for a per-session mutable field: `change_session_benchmark` (service + `PUT /sessions/{id}/benchmark` router + `BenchmarkSwitcher` UI). The per-trade transaction cost (`TRANSACTION_COST_USD` → `total_fees`), `record_trade`, position-closing, and `compute_session_value`/value-snapshot recording all already exist and are used by the rebalance executor.

## Goals / Non-Goals

**Goals:**
- Surface the session's asset scope on the session read model and the detail page.
- Allow changing the scope from the detail page, persisting it to `session_metadata`.
- On a narrowing change, immediately liquidate out-of-scope holdings with correct fees and a refreshed valuation, reusing existing trade/ledger/value machinery.

**Non-Goals:**
- No new DB column or migration for scope (it stays in JSON metadata).
- No change to how builds/rebalances/weekend crons consume scope (they already re-read it).
- No re-targeting or re-balancing of the remaining in-scope holdings as part of a scope change — only out-of-scope positions are sold; the next scheduled rebalance handles the rest.
- No change to the `max_asset_class_pct` guardrail logic.

## Decisions

### Keep scope in `session_metadata`; surface it as a typed read field
Add `asset_types: str` to `PaperTradingSessionRead`, defaulting to `AssetScope.BOTH.value`. Because the value lives in the JSON column (not an ORM attribute), `from_attributes` cannot auto-populate it; a model-level validator (or router-side population before `model_validate`) will read `session_metadata.get("asset_types", AssetScope.BOTH.value)`. Mirror the existing `AIBuildRequest.asset_types` field + `_validate_asset_types` validator for the literal set.
- *Alternative considered:* promote scope to a real column + migration. Rejected — no functional need, adds migration churn, and every consumer already reads metadata. Legacy rows (no `asset_types` key) correctly default to `both`.

### New `PUT /paper-trading/sessions/{id}/scope` mirroring the benchmark change
Thin router endpoint with a request body `{ asset_types }`, depending on `get_broker` (needed for liquidation). Error mapping: unknown session → 404 (`SessionNotFoundError`), unsupported scope → 422 (an invalid-scope domain error, validated via `AssetScope(value)`), broker `ConnectionError` → 503 (explicit mapping in the endpoint so the global handler is not relied upon). Returns the updated `PaperTradingSessionRead`.
- Service fn `change_session_scope(session, session_id, scope, broker)` in `paper_trading/service.py`: validate scope → `get_session` → compute out-of-scope liquidations (below) → mutate `session_metadata` by **reassigning the dict** (JSON column) so SQLAlchemy persists it → commit + refresh → return row.

### Liquidation only on genuine narrowing; reuse existing sell + ledger + value machinery
Compute `new_categories = scope_categories(new_scope)`. For each open position, resolve its `AssetClass` (crypto vs equity) the same way the rebalance builds its `asset_classes` map (universe class lookup), map to `AssetCategory`, and select positions whose category ∉ `new_categories`. If none, persist scope with **no** broker call (so widening / no-op never touches the broker). Otherwise, for each out-of-scope position: submit a sell through the broker, record the trade via the existing `record_trade` path (which applies `TRANSACTION_COST_USD` into `total_fees`), close the position in the ledger, then recompute and record the session value snapshot via the existing value-recording path.
- *Alternative considered:* route liquidation through the full two-phase rebalance executor. Rejected for this change — the executor is built around agent-produced target weights and buys; a scope narrowing is a pure sell-set. A focused sell loop reuses the same `record_trade`/close/value primitives without inventing agent targets. (Design note for apply: prefer an existing sell helper if one is already factored out of the executor; otherwise keep the loop in the service beside `change_session_scope`.)
- Unchanged-scope requests short-circuit before any liquidation computation.

### Frontend mirrors the benchmark switcher, plus a liquidation warning
Add `asset_types` to the `PaperTradingSession` TS type (reuse the `'stocks' | 'crypto' | 'both'` union already on the build-request type). Add `changeSessionScope` raw fn + `useChangeSessionScope` mutation hook (invalidate `paperTradingKeys.all` + kpis + valueHistory on success, since a narrowing moves value/KPIs). Render a read-only scope fact tile + a `ScopeSwitcher` `<select>` in `PaperTradingSessionPage`, mirroring the risk-guardrails tile and `BenchmarkSwitcher` (pending/error states).

### Determine "liquidation necessary" on the client to drive the warning
The session detail page already loads the session's open positions with their asset class (it renders the ledger and the asset-composition donut), so the UI can determine client-side whether a selected scope would liquidate: map the selected scope to its allowed categories and check whether any open position's category falls outside that set. When it would, the `ScopeSwitcher` SHALL show a confirmation warning naming that holdings will be sold, and only call the mutation after explicit confirmation; declining leaves the control on the current scope. A non-liquidating change requests immediately with no warning.
- *Alternative considered:* a backend "preview" endpoint that reports what a scope change would sell. Rejected as unnecessary — the client already has the positions and their classes; the authoritative liquidation still happens server-side in `change_session_scope`, so the client check is only for the UX warning, not correctness. If the position asset class is not reliably available client-side at apply time, fall back to warning on any narrowing (reduction of allowed categories) rather than skipping the warning.

## Risks / Trade-offs

- **Partial liquidation failure** (one sell fills, a later one errors) → the service performs sells before committing the metadata change where practical, and maps a broker failure to 503 so the caller sees the failure; positions already sold are recorded as real trades (consistent with how the executor records fills). Mitigation: keep the sell loop ordered and record each trade as it fills; document that a mid-loop broker outage can leave scope unchanged with some positions already sold (same failure shape as a rebalance interrupted mid-run).
- **Fees on forced liquidation** → each out-of-scope sell incurs `TRANSACTION_COST_USD`, intentionally, for consistency with all other trades; surfaced via `total_fees` and the refreshed value.
- **`max_asset_class_pct` guardrail becomes vacuous** when narrowing to a single asset class → acceptable; documented, no code change. The guardrail simply has nothing to cap.
- **Stub broker** → liquidation goes through the same `Broker` protocol; the stub fills immediately, so tests can assert the sells and fee accounting without network.

## Open Questions

None. A liquidating narrowing now requires an explicit confirmation warning in the UI (see the app-shell spec and the client-side determination decision above).
