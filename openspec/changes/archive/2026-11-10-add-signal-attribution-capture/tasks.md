# Tasks

> Revised at apply time (2026-11-10): price-ML and news-sentiment payloads are already
> captured via `trend_context`. See design "Revision at apply time".

## 1. Record what the run actually used

- [x] 1.1 In `flows/rebalance.py`, record the effective per-run opt-in set (`technical_indicators` when the trend gate applied; `fundamentals` / `price_ml` / `news_sentiment` when their block was attached) as a sorted list under `run_stats["enabled_signals"]`, an empty list when none applied. Verify: rebalance tests — a run with fundamentals + news enabled records exactly those two; a session whose toggle is on but whose prompt version predates the signal does not list it. (Crypto-only weekend runs reuse the same per-signal flags, whose `not crypto_only` gating existing tests already cover; there is no flow-level crypto-only harness, so no separate test was added.)
- [x] 1.2 In `flows/rebalance.py`, persist `trend_context["fundamentals"]` (`{candidates: [{ticker, fundamentals}], holdings: [{ticker, fundamentals}]}`) whenever the fundamentals block was attached, re-using the already-computed annotations. Verify: rebalance test — the recorded block matches what was attached to candidates and holdings, including any unavailable marker; nothing is recorded when fundamentals are off.

## 2. Surface it on the daily-run learning snapshot

- [x] 2.1 In `ai_portfolio/snapshots.py::_build_run_document`, add a top-level `enabled_signals` key taken from the run's `run_stats` (`null` on a no-run day or for runs predating the key). The per-signal payloads stay under the verbatim `run.trend_context`. Verify: snapshot tests — `enabled_signals` is recorded for a run; the fundamentals, price-ML and news blocks are present verbatim under `run.trend_context` with unavailable markers preserved; a no-run day records `enabled_signals: null` with valuation intact; an older run without the key degrades to `null`; re-assembly on the same day updates the single row.
- [x] 2.2 Confirm the backend-only contract: no read schema, API or frontend type gains `enabled_signals`, and `run_stats` stays unexposed. Verify: a test asserting the event read model has no `run_stats` / `enabled_signals` field.

## 3. Verify gates

- [x] 3.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`. Verify: all green; tear the Cadence DB container down.
- [x] 3.2 `openspec validate add-signal-attribution-capture --strict`. Verify: passes.
