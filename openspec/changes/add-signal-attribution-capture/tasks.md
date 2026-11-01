# Tasks

## 1. Capture the enabled opt-in signal set on the snapshot

- [ ] 1.1 In `ai_portfolio/service.py::assemble_daily_run_snapshots`, derive the set of opt-in signals that were enabled for the run from the session's frozen flags already in hand (`use_technical_indicators`, `use_fundamentals`, and whichever of `use_news_sentiment` / `use_price_ml` exist at apply time) and record it under a new `enabled_signals` key on the snapshot `document`.
- [ ] 1.2 Omit any signal flag that does not exist yet (older code paths / runs predating a signal) rather than referencing it unconditionally, so signal-free runs and older snapshots stay valid.

## 2. Capture the per-ticker signal payloads the agent was shown

- [ ] 2.1 In the assembly (and a `paper_trading` snapshot helper if one is the natural home), read the per-ticker signal blocks already persisted on the run (the fundamentals / news-sentiment / price-ML blocks attached in `flows/rebalance.py`, recorded via the run's payload / `trend_context` / `run_stats`) — do NOT re-fetch or re-score any signal.
- [ ] 2.2 Record, per enabled opt-in signal beyond technical indicators, the per-ticker payload (candidate, holding, and — for gated signals — dropped candidate) under additive keys in the `document`, preserving each signal's explicit `"unavailable"` marker verbatim where the run had no value for an asset.
- [ ] 2.3 Keep the existing technical-indicator block exactly as it is recorded today (no change to it).

## 3. Degradation and idempotency (preserve existing contract)

- [ ] 3.1 Ensure a day with a value snapshot but no run records valuation with the signal portions absent (mirroring the existing indicator/order-absent behavior); a day with no value snapshot is still skipped; a per-session failure still does not abort the batch.
- [ ] 3.2 Confirm re-running the assembly on the same calendar day still updates the single snapshot row (idempotent) with the new keys populated.

## 4. Tests

- [ ] 4.1 Unit-test that the assembly records `enabled_signals` for a run with one or more opt-in signals enabled.
- [ ] 4.2 Unit-test that the per-ticker signal payloads the agent was shown are recorded verbatim per candidate/holding for each enabled signal.
- [ ] 4.3 Unit-test that an `"unavailable"` signal value is preserved as unavailable (not invented, not dropped).
- [ ] 4.4 Unit-test that a run which enabled no opt-in signals (or predates a signal) records the snapshot with that signal omitted rather than erroring.
- [ ] 4.5 Unit-test that the backend-only contract holds — the new keys never surface in any read schema/API/frontend (assert the read model is unchanged).

## 5. Verify gates

- [ ] 5.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [ ] 5.2 `openspec validate add-signal-attribution-capture --strict`.
