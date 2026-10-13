## Why

The AI universe-evaluation agent recommends adding stocks that are **already in
the asset universe** (e.g. it told the operator to "add JNJ, PG, KO…" when JNJ
and PG are already held). The prompt is built from `_universe_summary`, which
collapses the full asset list into aggregate counts only — it never tells the
agent *which* tickers are present, so the agent guesses at gaps and names
well-known stocks that already exist. The output is misleading and undermines
trust in the feature.

## What Changes

- Feed the evaluation agent the universe's **actual roster, grouped by sector**:
  each holding rendered as `TICKER — Name` under its sector heading (with the
  per-sector count), ineligible assets flagged inline, crypto grouped too.
- Instruct the agent to suggest **only tickers that are NOT already in the
  roster**, both in the rendered prompt and in the system instructions.
- Keep the existing scope guardrails intact (US stocks + crypto only, long-only,
  no ETFs/funds/fixed-income/foreign listings). The universe stays stocks+crypto
  only — this change does **not** add ETF/fixed-income support.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `assets`: the "Generate and persist an AI evaluation" requirement — the
  evaluation prompt now includes the in-universe roster grouped by sector, and
  suggestions must not re-recommend assets already in the universe.

## Impact

- **Code:** `backend/src/cadence/assets/service.py` (`_universe_summary` builds
  the roster from the already-in-hand `assets` list — no new query);
  `backend/src/cadence/assets/universe_agent.py` (`UniverseSummary` gains a
  roster field, `build_universe_evaluation_prompt` renders a roster block +
  "only suggest absent tickers" instruction, `_AGENT_INSTRUCTIONS` reinforces
  it).
- **Out of scope:** no per-asset market-cap/liquidity/quality figures in the
  prompt; no change to the agent's tools (still tool-less), structured output,
  model, timeout, caching/fingerprint, persistence, API, or the frontend panel;
  no migration or schema change; no change to *when* evaluation runs.
- **Tests:** unit tests for the roster build and the prompt block; updates to
  existing prompt/summary tests. No frontend changes.
