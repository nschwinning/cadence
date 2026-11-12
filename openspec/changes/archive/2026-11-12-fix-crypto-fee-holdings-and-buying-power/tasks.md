## 1. Backend

- [x] 1.1 Book crypto buys net of `CRYPTO_FEE_PCT` in `book_fill` (trade keeps filled qty, fee once) and close a ≤1% crypto ledger remainder on sells; verify with pytest (1,000 ADA → 997.5 at $0.50, fees +$1.25, equity unchanged, capped full exit leaves no remainder).
- [x] 1.2 Cap AI-portfolio crypto sells at the account's holding and raise `MIN_CRYPTO_NOTIONAL_USD` to 10; verify with pytest (exit 0.0001 over the holding sells the holding; $6 crypto buy skipped below minimum).
- [x] 1.3 `AccountInfo.cash_buying_power` from Alpaca `non_marginable_buying_power`; overview/schema `cash_buying_power`; verify parsing and endpoint tests.
- [x] 1.4 Admin: `PositionRow.write_off_eligible/write_off_quantity`, `write_off_positions`, `POST /admin/write-off-positions`, crypto `below_minimum` skip in Restore/Flatten, eligible rows not restorable; verify with pytest (600/400 vs 997.5 → 598.5/399 at same cost and no order; 5% gap skipped; equity skipped; 0.0226 SOL restore skipped below minimum).
- [x] 1.5 Close explicitly rejected admin orders in the journal at once; verify the rejected restore row is resolved and not listed as unresolved.

## 2. Frontend

- [x] 2.1 Types; Admin page: cash and margin buying power, Write off / Write off all with confirmation and outcomes (`written_off`, `below_minimum` reason text); tile capped at the lower buying power; verify with vitest (write-off confirm/cancel posts symbol only, figures labelled, tile shows $30,000 for 40k free / 30k cash / 325k margin).

## 3. Verification

- [x] 3.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 3.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 3.3 `openspec validate fix-crypto-fee-holdings-and-buying-power --strict` passes.
