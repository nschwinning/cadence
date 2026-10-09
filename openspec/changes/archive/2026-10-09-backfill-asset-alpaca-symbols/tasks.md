## 1. Implement the backfill helper

- [x] 1.1 In `backend/src/cadence/assets/service.py`, add `backfill_alpaca_symbols(session: Session, broker: Broker) -> int` as a sibling of `backfill_fractionable`: select assets where `Asset.alpaca_symbol.is_(None)`; for each, derive `asset_class` from `asset.category` (CRYPTO vs EQUITY), call `broker.get_asset(asset.ticker, asset_class)` inside a `try/except Exception` that `logger.warning(...)`s and `continue`s; when the result is not None and `.tradable`, set `asset.alpaca_symbol = broker_asset.symbol` and increment the counter; `session.commit()` only if any row changed; return the count. Verify with `uv run ruff check .` and `uv run mypy src/cadence`.

## 2. Tests

- [x] 2.1 In `backend/tests/test_assets_service.py`, add a test mirroring `test_backfill_fractionable_populates_null_rows_fail_open`: seed assets with `alpaca_symbol=None` whose tickers map (via a fake/stub broker) to a tradable asset with a *matching* symbol, a tradable asset with a *differing* canonical symbol (e.g. `BRK-B` → `BRK.B`), a not-listed/None result, and a raising lookup; assert the matching and differing symbols are stored (differing one stored as the broker's canonical symbol), the None and raising rows stay `None`, and the returned count equals the number actually filled. Verify with `uv run pytest -k backfill_alpaca`.
- [x] 2.2 Add a test mirroring `test_backfill_fractionable_is_idempotent`: run the backfill twice and assert the second run updates zero rows and leaves already-populated `alpaca_symbol` values unchanged. Verify with `uv run pytest -k backfill_alpaca`.

## 3. Verify gates

- [x] 3.1 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` and confirm all pass (frontend unaffected — no change).
