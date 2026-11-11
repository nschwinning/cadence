## Why

Cadence is growing a family of **opt-in rebalance signals** — the technical-indicator
trend strategy and company fundamentals today, plus news sentiment and a learned price-ML
direction signal in flight. Each is offered as a per-session toggle on the premise that it
helps the AI make better decisions, but the project has **no way to measure whether any of
them actually does**. The existing consolidated daily-run learning snapshot already records
the *technical-indicator* values the agent saw alongside that day's run, outcome
statistics, filled orders, and P&L — but it does **not** record the other signals the agent
was shown (fundamentals, news sentiment, price-ML), nor which opt-ins were enabled for the
run. Without that, an offline analysis cannot attribute a session's outcomes to the signals
that drove them.

This change closes that gap: it extends the backend-only daily-run learning snapshot to
capture, for each run, **which opt-in signals were enabled** and **the exact per-ticker
signal payloads the agent was shown** for each one — reusing data already assembled on the
run, with no recompute and no new user-facing behavior. Because the snapshot is already
keyed per session per calendar day and already carries that day's valuation and
per-position P&L, recording the shown signals in the same row makes signal-to-outcome
attribution a pure offline join over the existing daily series.

## What Changes

- **ai-paper-trading** (modified): the **Consolidated daily-run learning snapshot** gains,
  in addition to the technical-indicator values it already records, (1) the **set of
  opt-in signals enabled** for the run (trend, fundamentals, news sentiment, price-ML —
  whichever exist and were on) and (2) the **per-ticker signal payloads the agent was
  shown** for each enabled signal — per candidate, per holding, and (for the gated signals)
  per dropped candidate — including the explicit "unavailable" marker where a signal had no
  value for an asset. These are consolidated from data already attached to the run (the
  blocks the rebalance flow assembles and persists), without re-fetching or re-computing
  any signal. The snapshot stays **backend-only** (no read schema, API, or frontend) and
  idempotent per session per day, exactly as today.

## Capabilities

### Modified Capabilities

- `ai-paper-trading`: the consolidated daily-run learning snapshot additionally records the
  enabled opt-in signal set and the per-ticker signal payloads the agent was shown, so each
  day's AI decision is fully attributable to the signals that informed it.

## Impact

- **Backend:** extend the daily-run snapshot assembly (`ai_portfolio/service.py::assemble_daily_run_snapshots`
  and the `paper_trading` snapshot helpers) to pull the per-run signal payloads already
  persisted on the rebalance run (the fundamentals / news-sentiment / price-ML blocks and
  the enabled-flag set) into the snapshot `document`. No new table — the existing
  `session_daily_run_snapshots.document` JSONB absorbs the additional keys. No new column,
  no schema/API/frontend change.
- **No recompute:** the signals are read from what the run already recorded; the assembly
  only consolidates.
- **No change** to when/how signals are attached during a rebalance, to the AI output
  schema, the executor, valuation, guardrails, or scheduling.

## Assumptions (for review)

1. **Follow-up, not a prerequisite.** This change records whatever signals exist at apply
   time and degrades gracefully as more are added — it is intended to ship **after** at
   least one of `add-news-sentiment-rebalance` / `add-price-ml-rebalance` so there is a new
   signal to capture, but it does not block them and they do not block it.
2. **Backend-only, consistent with the existing snapshot.** The captured attribution is for
   export / offline learning only; it is never surfaced in a read model, API, or UI.
3. **Consolidation only.** The per-ticker signal payloads are taken verbatim from what the
   run recorded (the same blocks the agent saw); this change neither re-derives signals nor
   computes forward returns inline — outcome attribution is a downstream offline join over
   the existing per-day valuation series already in the snapshot.
4. **Schema-additive within the JSONB `document`.** New keys are added to the existing
   snapshot document; days/runs that lack a given signal simply omit it or mark it
   unavailable, so older snapshots and signal-free runs remain valid.
