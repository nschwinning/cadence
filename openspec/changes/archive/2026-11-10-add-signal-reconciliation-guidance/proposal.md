## Why

Cadence is accumulating a family of **opt-in rebalance signals** — technical-indicator
trend and company fundamentals today, news sentiment and a learned price-ML direction
signal in flight. Each attaches its own per-ticker advisory block to the rebalance prompt.
With several enabled at once, two problems emerge that none of the individual signal
changes address:

1. **Conflicting advice with no reconciliation rule.** The agent can be shown a bullish
   trend block, a bearish sentiment block, and a neutral price-ML block for the same
   ticker, with no instruction on how to weigh them against each other. Each signal's
   prompt section is written in isolation ("weigh it when present"), so the combined prompt
   never tells the agent what to do when signals disagree.
2. **No guidance to the operator that stacking signals can dilute focus.** The build form
   lets a session turn on every signal; nothing hints that a focused 2–3 complementary
   signals usually serve a strategy better than all of them at once.

This change addresses both **without** a hard cap on how many signals a session may enable
(the signals are complementary lenses — trend for timing, fundamentals for quality,
sentiment for catalysts, price-ML for learned direction — and legitimately combine), and
**without** changing any individual signal's attachment logic or the long-only output
contract.

## What Changes

- **ai-paper-trading** (modified): a new **signal-reconciliation** section is added to the
  rebalance prompt, delivered as a **new rebalance prompt version** (cumulative, per the
  versioned-prompt requirement). When a session is frozen on a prompt version at or after
  the reconciliation-aware version, the prompt instructs the agent how to treat multiple
  advisory signal blocks: all signals are advisory inputs to its judgement (never a
  mechanical tilt); when signals **converge** that strengthens the case; when they
  **conflict** the agent SHALL resolve the conflict in its reasoning and note it in the
  thesis rather than silently following one block; and the agent SHALL stay within the
  existing long-only / weights-~1.0 / transaction-cost discipline. The section reads
  correctly whether zero, one, or several signal blocks are actually attached (defensive,
  like the fundamentals-aware version). No change to which blocks attach or to the output
  schema. This is a follow-up that is only meaningful once more than one opt-in signal
  exists; it does not block the signal changes and they do not block it.

- **app-shell** (modified): the AI build form shows a **soft, non-blocking hint** when a
  session has three or more opt-in signals toggled on (for example "Using many signals can
  dilute focus — 2–3 complementary signals usually work best"). It is advisory only: it
  does not disable the build, does not cap or uncheck any toggle, and does not change the
  submitted request.

## Capabilities

### Modified Capabilities

- `ai-paper-trading`: the rebalance prompt gains a version-gated signal-reconciliation
  section telling the agent how to weigh multiple advisory signal blocks and how to handle
  convergence and conflict, without changing signal attachment or the output contract.
- `app-shell`: the AI build form gains a soft, non-blocking hint when three or more opt-in
  signals are enabled.

## Impact

- **Backend:** a new seeded rebalance prompt version (bump the prompt-version constant to
  the next free value at apply time) whose instructions add the reconciliation section;
  the template is otherwise byte-identical to the then-head version. No new flag, no
  migration beyond the prompt-seed migration, no change to `flows/rebalance.py` attachment
  logic, the AI output schema, the executor, valuation, guardrails, or scheduling.
- **Frontend:** a soft hint in `BuildAIPortfolioCard` keyed off the count of enabled opt-in
  toggles; no new type, request field, or API change.

## Assumptions (for review)

1. **Follow-up, not a prerequisite.** The reconciliation section is only useful once two or
   more opt-in signals can be attached, so this is intended to ship **after** at least one
   of `add-news-sentiment-rebalance` / `add-price-ml-rebalance`. It does not block them and
   they do not block it.
2. **No hard cap.** We deliberately do **not** limit how many signals a session may enable,
   in code or in the UI — the signals are complementary and a cap cannot know which
   combination is right for a given strategy. The UI hint is advisory only.
3. **Prompt-level reconciliation, not weight post-processing.** The guidance is prompt text
   the agent reasons over; we do not mechanically adjust target weights by signal agreement.
   The long-only / weights-~1.0 output contract is unchanged.
4. **Cumulative, version-gated prompt.** The reconciliation-aware version = the then-head
   prompt verbatim + the reconciliation section; it takes the next free prompt version at
   apply time (after whichever of sentiment / price-ML ships last). Sessions frozen on an
   earlier version are unaffected.
5. **Soft hint threshold.** Three or more enabled opt-in signals triggers the hint; the
   exact copy and threshold are confirmed at apply time. Counting covers the opt-in signals
   that exist at apply time (trend, fundamentals, and whichever of sentiment / price-ML have
   shipped).

## Sequencing with the other in-flight AI-signal changes

This change touches the **same rebalance prompt version line** as `add-news-sentiment-rebalance`
and `add-price-ml-rebalance` and therefore MUST be built **after** them and **sequentially**,
never in parallel, to avoid colliding on the prompt-version number. Rebalance prompt versions
are linear and cumulative (each version = the prior version's text verbatim + one new block /
section). The reconciliation-aware version SHALL take the next free version after the last of
the signal changes to ship, and its seed prompt SHALL be that then-current head prompt
verbatim + the reconciliation section. A session frozen at an earlier version never gains the
reconciliation guidance — the expected build-time-frozen behavior.
