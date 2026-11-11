## Context

Each opt-in rebalance signal (`add-fundamentals-rebalance-prompt` today, plus
`add-news-sentiment-rebalance` / `add-price-ml-rebalance` in flight) attaches its own
per-ticker advisory block in `flows/rebalance.py` and ships a new, cumulative rebalance
prompt version whose instructions describe that one block "weigh it when present, tolerate
its absence." No version describes how to weigh the blocks **against each other**. With two
or more signals enabled, the agent can be shown contradictory advice with no reconciliation
rule, and the operator gets no hint that stacking every signal can dilute a strategy.

This change is a thin, prompt-and-UI-level follow-up: one more cumulative prompt version
adding a reconciliation section, and a soft UI hint. It deliberately avoids a hard cap on
signal count.

## Goals / Non-Goals

**Goals**
- Give the rebalance agent an explicit rule for weighing multiple advisory signal blocks:
  advisory-only, convergence strengthens, conflict must be resolved and surfaced,
  "unavailable" means absence.
- Nudge the operator, non-blockingly, toward a focused signal set.
- Stay entirely within the existing versioned-prompt and opt-in patterns; change no signal
  attachment logic and no output contract.

**Non-Goals**
- **No hard cap** on how many signals a session may enable (code or UI).
- No weight post-processing by signal agreement — reconciliation is the agent's judgement.
- No new per-session flag, no new backend request field, no migration beyond the prompt seed.
- No change to `flows/rebalance.py` attachment, the AI output schema, executor, valuation,
  guardrails, or scheduling.

## Decisions

### Deliver reconciliation as one more cumulative prompt version
The reconciliation-aware version = the then-head rebalance prompt verbatim + a new
reconciliation section in the **instructions** part (the system persona/requirements), with
the **input template** byte-identical to the head version. It is version-gated exactly like
the fundamentals-aware version: only sessions frozen at or after it get the section, and the
section is written defensively so a session with one or zero attached blocks still reads
correctly. This reuses the existing seed-migration + `*_PROMPT_VERSION` bump mechanics with
no new moving parts.

### Section content, not weights
The section instructs the agent to treat every attached block as advisory, to strengthen its
case on convergence, to resolve-and-surface conflicts in the thesis, and to read an
"unavailable" marker as absence (not a negative). It adds **no** rule that mechanically
alters target weights — consistent with every signal being "advisory, not a deterministic
tilt."

### Soft UI hint, count-based, non-blocking
`BuildAIPortfolioCard` already renders the opt-in toggles. The hint derives purely from the
count of enabled opt-in toggles (≥3 → show), with no effect on the toggles, the build
button, or the submitted request. It is a pure presentational addition — no new type or API.

### Sequencing
Because this shares the prompt-version line with the two signal changes, it must be built
after them, sequentially, taking the next free version and seeding from the then-head. See
the proposal's sequencing section.

## Risks / Trade-offs

- **Prompt length growth.** One more instructions section adds tokens to every run on the new
  version. Bounded (a short paragraph) and only on sessions frozen at the new version.
- **Guidance the agent may underweight.** Prompt guidance is advisory by nature; the
  reconciliation rule improves conflict handling but cannot guarantee it. Acceptable — the
  alternative (mechanical weight adjustment) is explicitly out of scope and riskier.
- **Threshold choice.** "≥3" is a judgement call; it is a soft hint only, so the cost of a
  wrong threshold is low and it is trivially tunable at apply time.

## Migration Plan

One prompt-seed migration appends the reconciliation-aware version (head text + section);
`*_PROMPT_VERSION` is bumped to that value. No column, no data backfill. Existing sessions
keep their frozen version untouched. Rollback is not seeding/activating the new version;
already-built sessions are unaffected either way.

## Open Questions

- Final prompt-version number — resolved at apply time to the next free value after the last
  signal change ships (sequencing section).
- Exact hint copy and whether the threshold should be ≥3 or configurable — confirm at apply
  time; proposed ≥3 with the copy in the proposal.
- Whether "technical indicators" counts toward the hint's signal tally or only the newer
  opt-ins — proposed: count every opt-in toggle present on the form at apply time.
