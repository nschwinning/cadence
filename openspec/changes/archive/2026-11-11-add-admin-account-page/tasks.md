## 1. Broker groundwork

- [x] 1.1 Add optional `asset_class: AssetClass | None = None` to the broker `Position` dataclass and set it in `AlpacaBroker._parse_position` from Alpaca's `asset_class`; verify with a broker unit test parsing an equity and a crypto (`BTCUSD`) position.

## 2. Reconciliation service

- [x] 2.1 Create `cadence/admin/service.py` with the normalised symbol key (`-`, `/`, `.` stripped, upper-cased) and the per-symbol comparison (Cadence qty = all AI `SessionPosition`s + all `BotPosition`s, any status; classification matched/orphan/shortfall/short with ε = 1e-6; `pending_order`; `flattenable`); verify with pytest covering outsider-only symbol, shared symbol (15 vs 10 → orphan 5), stopped-bot positions counted, shortfall, short, pending order, `BRK.B`↔`BRK-B` and `BTCUSD`↔`BTC-USD` matching.
- [x] 2.2 Add the committed-cash check (active AI session cash via allocated + total_pnl − fees − ledger cost; active bot cash; active orchestrator free capital; stopped unreturned orchestrator bots' cash; manual stopped bots excluded) with itemised contributors, total, difference and shortfall flag; verify with pytest for covered vs shortfall and contributor itemisation, asserting no DB row changes.
- [x] 2.3 Add the account overview assembler (account figures + cash check + open orders + comparison) returning a broker-unavailable result on `BrokerError`; verify with pytest using `StubBroker` and a failing broker.
- [x] 2.4 Add `flatten_orphans(symbol | None)` that recomputes at execution, ignores client quantities, skips not_orphan / pending_order / market_closed (equities only) / not_found, sells exactly the orphan quantity with the right asset class, catches `BrokerError` per symbol, logs outcomes and writes nothing to the DB; verify with pytest for single sell, changed quantity, no-longer-orphan skip, closed-market equity skip vs crypto sold, flatten-all continuing past a rejection, and ledgers/trades/orchestrator capital unchanged.

## 3. API

- [x] 3.1 Add response/request schemas to `api/schemas.py` and `api/routers/admin.py` (`GET /api/v1/admin/account` always 200 with `broker_available`; `POST /api/v1/admin/flatten-orphans` with body `{symbol: str | null}`, 503 when the broker cannot be read), register the router; verify with endpoint tests (shape, unavailable broker, flatten single/all, a client-sent quantity field rejected or ignored).

## 4. Frontend

- [x] 4.1 Add TS types and `api/admin.ts` (`useAdminAccount` with manual refetch, `useFlattenOrphans` mutation invalidating the account query); verify via the page tests below.
- [x] 4.2 Build `pages/admin/AdminPage.tsx` (Account, Cash check with shortfall warning, Open orders, Positions with status per row, per-row Flatten + "Flatten all orphans", confirmation modal listing symbols/quantities with the "recomputed at execution" note, outcome list, broker-unavailable state); verify with vitest: figures render, shortfall warning, non-flattenable rows show status and no button, cancel submits nothing, confirm posts `{symbol}` (no quantity) and shows outcomes, flatten-all hidden when nothing is flattenable, unavailable state.
- [x] 4.3 Add the "Admin" sidebar entry directly after "System" (new icon) and the `/admin` route; verify with a Sidebar/App test asserting order and navigation.

## 5. Verification

- [x] 5.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 5.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 5.3 `openspec validate add-admin-account-page --strict` passes.
