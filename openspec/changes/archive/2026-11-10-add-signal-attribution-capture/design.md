## Context

The consolidated daily-run learning snapshot (`session_daily_run_snapshots`, assembled by
`ai_portfolio/service.py::assemble_daily_run_snapshots`, one JSONB `document` per session
per calendar day) already consolidates — without recompute — the day's rebalancing run,
the AI reasoning/result, the **technical-indicator** values the agent saw, the run's
outcome statistics, the day's reconciled filled orders, and the day's P&L/valuation. It is
backend-only and idempotent per session per day.

As more opt-in signals are added (news sentiment, price-ML), the agent is shown more than
indicators, but the snapshot still only captures the indicator block. This change records
the rest, so an offline analysis can ask "did fundamentals / sentiment / price-ML help?"
by joining the shown signal on day D to the per-position outcome already recorded on later
days.

## Goals / Non-Goals

**Goals**
- Record, in the existing snapshot `document`, the **set of opt-in signals enabled** for
  the run and the **per-ticker payloads the agent was shown** for each enabled signal
  beyond the indicators (fundamentals, news sentiment, price-ML), per candidate / holding /
  dropped candidate, preserving each signal's "unavailable" marker.
- Consolidate only — read the payloads from what the run already persisted; no re-fetch, no
  re-score, no agent re-run.
- Stay backend-only, idempotent, and additive (older snapshots and signal-free runs remain
  valid).

**Non-Goals**
- No new table or column (the JSONB `document` absorbs the new keys).
- No read schema / API / frontend exposure.
- No change to how signals are attached during a rebalance, to the AI output schema, the
  executor, valuation, guardrails, or scheduling.
- **No inline outcome/forward-return computation** — attribution is a downstream offline
  join over the per-day valuation series already in the snapshot; this change only records
  the inputs cleanly.

## Decisions

### Source the payloads from the run, not from the live signal services
The rebalance run already assembles each signal block and persists the per-run picture
(the technical-indicator context is recorded today via the run's `trend_context`; the
price-ML tasks extend that same recorded context, and fundamentals/sentiment attach the
same way). The assembly reads those persisted structures straight out of the run's recorded
payload/`trend_context`/`run_stats`. This keeps the "consolidate, never recompute"
invariant the existing requirement already states and guarantees the snapshot reflects
exactly what the agent saw.

### Store under additive keys in the existing `document`
Add an `enabled_signals` key (the set/list of opt-in signals in effect for the run) and a
per-signal, per-ticker payload map alongside the indicator block already stored, keyed so a
reader can line each signal up with each candidate/holding. No migration — `document` is
JSONB. Runs that lack a signal omit its key; assets a signal couldn't score keep the
"unavailable" marker verbatim.

### Degrade exactly like the existing snapshot
A day with a value snapshot but no run records the valuation with the signal portions
absent (as it already does for the indicator/order portions); a day with no value snapshot
is skipped; assembly for one session failing never aborts the batch. No new failure modes.

### Revision at apply time (2026-11-10)
Two assumptions above no longer hold against the shipped code, so the approach is adjusted
(the spec is unchanged):

- **Price-ML and news sentiment are already captured.** Their changes write each per-ticker
  block, including the "unavailable" marker, into the run's `trend_context`, and the
  snapshot already copies `trend_context` verbatim under `document.run.trend_context`. No
  extra snapshot key is needed for them, and duplicating them would only invite drift.
- **Fundamentals are not stored on the run.** They are attached to candidates and holdings
  for the prompt but never persisted, so the snapshot cannot read them. The rebalance flow
  therefore writes `trend_context["fundamentals"]`, with the same candidates/holdings shape
  as price-ML and news, whenever the fundamentals block was attached. This is the
  only change to `flows/rebalance.py`, and it re-uses the already-computed annotations, so
  nothing is re-fetched.
- **The "enabled" set must be the effective per-run set, not the session toggles.** A toggle
  only takes effect when the session's frozen prompt version supports it, and fundamentals,
  price-ML and news are skipped on crypto-only weekend runs. The run computes exactly these
  effective flags (`gating_enabled`, `fundamentals_enabled`, `price_ml_enabled`,
  `news_sentiment_enabled`). It records them as a sorted list under
  `run_stats["enabled_signals"]` (`run_stats` is already backend-only), and the snapshot
  surfaces that list as `document.enabled_signals` (`null` on a day without a run).
  Deriving the set from the session flags in the assembly, as originally planned, would
  label signals as enabled for runs where the AI never saw them.

## Risks / Trade-offs

- **Document growth:** adding per-ticker blocks for several signals enlarges each JSONB
  `document`. Bounded by the universe size per run; acceptable for a backend-only learning
  record and far smaller than, e.g., the research transcripts already stored on events.
- **Coupling to the recorded run shape:** the assembly depends on the signal blocks being
  present in the run's recorded payload. Mitigated because each signal change already
  records its block on the run; this change only reads it, and omits cleanly when absent.
- **Attribution is offline, not in-app:** intentionally — this change provides clean inputs,
  not a verdict. A separate analysis (out of scope) joins signal → forward outcome.

## Migration Plan

No schema migration — the change is purely additive within the existing
`session_daily_run_snapshots.document` JSONB. Existing snapshots remain valid; new keys
appear only on snapshots assembled after this ships. No backfill. Rollback is removing the
assembly code that populates the new keys; already-written documents are harmless extra
keys.

## Open Questions

- Exact JSON shape of the per-signal payload map (one nested object per signal vs a flat
  per-ticker record carrying all signals) — finalize during apply for easiest offline
  querying; proposed one nested object per signal mirroring how the blocks are attached.
- Whether to also record, per candidate/holding, the **as-of price** the signal was keyed
  to (to make the offline forward-return join exact without re-deriving it) — proposed yes
  if it is already on the recorded block, otherwise rely on the day's value snapshot.
