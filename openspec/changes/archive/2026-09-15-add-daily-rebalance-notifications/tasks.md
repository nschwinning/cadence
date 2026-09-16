## 1. Notify capability (Pushover)

- [x] 1.1 `config.py`: add `PUSHOVER_USER: str = ""` and `PUSHOVER_TOKEN: str = ""` to `Settings`, with comments noting both are optional and empty disables notifications. Document them in root `.env.example` under a new "Push notifications (optional)" section.
- [x] 1.2 New `cadence/notify/base.py`: `@runtime_checkable` `Notifier` protocol — `send(self, message: str, *, title: str | None = None) -> bool` (returns whether delivery was attempted+ok). Add a `NotifyError` if useful. Keep it I/O-free.
- [x] 1.3 New `cadence/notify/pushover.py`: `PushoverNotifier` posting to `https://api.pushover.net/1/messages.json` via `requests` (short timeout), reading creds from `settings`. Missing creds → log + return False without a network call. Transport/non-2xx → log a warning + return False (never raise). Adapt from `trading-bot/.../tools/pushover_tool.py`.
- [x] 1.4 New `cadence/notify/null.py`: `NullNotifier` — a no-op `send` returning False. New `cadence/notify/__init__.py`: export `Notifier`, `PushoverNotifier`, `NullNotifier`, `get_notifier`; `get_notifier()` returns `PushoverNotifier()` when both creds are set, else `NullNotifier()`. Verify: `mypy`/`ruff` clean; protocol satisfied by both impls.

## 2. Thread a Notifier down the daily rebalance path (daily-only)

- [x] 2.1 `ai_portfolio/background.py`: `start_rebalance(...)` and `_job_rebalance(...)` gain an optional `notifier: Notifier | None = None`, forwarded into `service.run_rebalance_event`. Default `None` keeps manual/build callers unchanged. Import the `Notifier` protocol.
- [x] 2.2 `ai_portfolio/service.py`: `run_rebalance_event(..., notifier: Notifier | None = None)`. On the executed-orders success path (when `executed > 0`, before/after `_finish_event`), build a summary message (portfolio name, order count, per-order `BUY/SELL <ticker>` from `trade_results`, realized P&L) and call `notifier.send(...)` when `notifier is not None`. In the `except` failure handler, when `notifier is not None`, send a brief failure message (event id + reason). Wrap every `notifier.send(...)` in try/except that only logs — a notify failure must never affect the event/run. Do NOT notify on the market-closed/skip branch.
- [x] 2.3 `api/routers/ai_portfolio.py`: the daily endpoint `rebalance_daily` resolves `notifier: Annotated[Notifier, Depends(get_notifier)]` and passes it to `start_rebalance(..., notifier=notifier)`. The manual endpoint `rebalance_session` continues to call `start_rebalance(...)` with no notifier (so manual never notifies). Verify: `mypy` clean.

## 3. Tests

- [x] 3.1 `notify` unit tests: `PushoverNotifier` posts the expected payload on success (monkeypatch `requests.post`); returns False + no network call when creds missing; returns False (no raise) on transport error / non-2xx. `NullNotifier.send` is a no-op returning False.
- [x] 3.2 Add a recording fake notifier to `tests/fakes.py` (records sent messages). Service tests via the daily path: notifies once with order details when orders are executed; notifies on failure; does NOT notify on market-closed skip or zero-order run; a notifier that raises does not fail the rebalance (event still SUCCEEDED/PARTIAL and run recorded).
- [x] 3.3 Confirm a manual rebalance (no notifier injected) sends nothing even when orders execute.

## 4. Verification

- [x] 4.1 Backend: `uv run pytest` green, `uv run ruff check .` clean, `uv run mypy src/cadence` clean.
- [x] 4.2 `openspec validate add-daily-rebalance-notifications --strict` passes.
- [x] 4.3 Manual smoke (optional): with `PUSHOVER_USER`/`PUSHOVER_TOKEN` set and `ALPACA_STUB=true`, trigger the daily endpoint with a session that executes stub orders and confirm a push arrives; unset creds and confirm the run still succeeds with no push.
