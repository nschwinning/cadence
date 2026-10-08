## 1. Audit the equity order type / TIF (blocking prerequisite)

- [x] 1.1 Inspect the equity order path in `broker/alpaca.py` (`submit_order`/`buy`/`sell`) and the executor to determine the order type and `time_in_force` currently sent for equity orders. Record the finding in a comment on the relevant code and confirm whether it already satisfies Alpaca's fractional constraint (market or day-limit, TIF=day). Verify by reading the submitted payload and adding/confirming a broker-level test that asserts the equity order type and TIF.

## 2. Persist fractionability on the asset

- [x] 2.1 Add a nullable `fractionable: Mapped[bool | None]` column to `assets/models.py`. Verify with a model/import test and (after task 2.2) a migration round-trip.
- [x] 2.2 Add a schema-only Alembic migration adding the nullable `fractionable` column, `down_revision` = current head. Verify `uv run alembic upgrade head` then `downgrade` runs clean and `uv run alembic check` reports no drift.
- [x] 2.3 In `assets/service.py::add_asset`, set `fractionable` from the `BrokerAsset` already fetched for the tradability check (no extra broker call). Verify with a service test asserting a newly added fractionable asset stores `fractionable=True` and a non-fractionable one stores `False`.
- [x] 2.4 Add `backfill_fractionable(session, broker)` in `assets/service.py` that iterates rows where `fractionable IS NULL`, calls `broker.get_asset` once each, sets the flag, and swallows per-asset errors leaving `NULL` (idempotent, fail-open). Verify with a test using a fake broker that mixes fractionable/non-fractionable/raising tickers and asserts the resulting flags (raiser stays `NULL`).

## 3. Executor fractional equity sizing

- [x] 3.1 Add `EQUITY_QTY_PRECISION` (6) and `MIN_EQUITY_NOTIONAL_USD` constants in `ai_portfolio/executor.py` alongside the crypto constants. Verify they are referenced by the sizing code (tasks 3.2–3.4) and covered by the new tests.
- [x] 3.2 Thread each equity's `fractionable` flag into sizing: load it from the in-scope asset rows the executor already fetches, defaulting unknown/`NULL` to non-fractionable. Verify with a test asserting the executor reads the flag off the asset record (no per-ticker broker call added).
- [x] 3.3 In `_open_long` (build buy), size fractionable equities as `round(capital / price, EQUITY_QTY_PRECISION)` skipping only when `qty * price < MIN_EQUITY_NOTIONAL_USD`; keep `float(int(capital / price))` + `< 1 share` skip for non-fractionable. Verify with executor tests: a fractionable name that doesn't divide evenly places a fractional order; a non-fractionable name still truncates to whole shares; a sub-threshold fractionable allocation is skipped and recorded as not executed.
- [x] 3.4 In `_plan_equity` (rebalance), for fractionable assets compute `current`/`target`/`delta` as rounded floats and gate on `abs(delta) * price >= MIN_EQUITY_NOTIONAL_USD`; keep integer-share delta with `|delta| >= 1` guards for non-fractionable. In the equity close/exit path, sell the full fractional `pos.quantity` for fractionable assets and keep `float(int(abs(pos.quantity)))` for non-fractionable. Verify with rebalance/exit tests covering a fractional buy delta, a fractional sell/exit, and the non-fractionable whole-share paths unchanged.
- [x] 3.5 If task 1.1 found the equity order type/TIF does NOT satisfy Alpaca's fractional constraint, adjust the executor/broker so fractional equity orders are submitted as a market or day-limit order with TIF=day, leaving whole-share orders unchanged. Verify with a test asserting the submitted fractional equity order's type and TIF. (If 1.1 found it already compliant, mark this done with a note and the assertion from 1.1.) NOTE: task 1.1 found the equity order path already compliant (buy/sell default to `OrderType.MARKET` + `TimeInForce.DAY`; `_effective_tif` only diverts crypto to GTC), so no order-path change was needed — only the assertion test `test_fractional_equity_buy_posts_market_day_and_fractional_qty` in `test_broker_alpaca.py` plus the confirming comment in `AlpacaBroker.submit_order`.

## 4. Verification

- [x] 4.1 Confirm no change to the AI agent output schema (`ai_portfolio/agent.py`) and no frontend change: `git status` shows changes only under `backend/`.
- [x] 4.2 Run the backend gate green: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 4.3 Run `openspec validate add-fractional-equity-sizing --strict` and resolve any issues.
