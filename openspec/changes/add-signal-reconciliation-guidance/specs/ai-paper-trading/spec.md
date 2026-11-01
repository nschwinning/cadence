## ADDED Requirements

### Requirement: Rebalancing prompt reconciles multiple advisory signals

The system SHALL provide a **signal-reconciliation** section in the rebalance prompt,
delivered as a new rebalance prompt version (per the versioned-prompt requirement). When a
session is frozen on a prompt version at or after the reconciliation-aware version, its
rebalance prompt SHALL instruct the agent how to weigh the per-ticker advisory signal blocks
that may be attached (technical indicators, company fundamentals, news sentiment, and the
price-ML direction signal — whichever exist and are attached for that run):

- all attached signals are **advisory inputs to the agent's judgement**, never a mechanical
  weight tilt;
- when signals **converge** for a ticker, that SHALL be treated as strengthening the case
  for the corresponding action;
- when signals **conflict** for a ticker, the agent SHALL resolve the conflict in its
  reasoning and surface it in the thesis rather than silently following a single block or
  ignoring the disagreement;
- an **"unavailable"** marker on any signal SHALL be treated as absence of that signal for
  that ticker, not as a negative reading.

The reconciliation section SHALL be written **defensively** so that the prompt reads
correctly whether zero, one, or several signal blocks are actually attached for a run — a
session that enabled only one signal, or none, SHALL read correctly on the
reconciliation-aware version with nothing to reconcile. A session frozen on a prompt version
predating the reconciliation-aware version SHALL receive no reconciliation section and SHALL
behave exactly as it did before this change.

This requirement SHALL NOT change which signal blocks attach to candidates or holdings, the
per-session opt-in flags, the AI output schema, or any existing rebalance constraint
(long-only, target weights summing to approximately 1.0, per-trade transaction-cost
discipline, crypto handled with around-the-clock tickers, discovery and web-search caps); an
omitted or ~0-weight holding still means sell/exit.

#### Scenario: Reconciliation-aware prompt guides conflict handling

- **WHEN** a rebalance runs for a session frozen on the reconciliation-aware prompt version
  (or later) with two or more advisory signal blocks attached for a ticker
- **THEN** the prompt SHALL instruct the agent to weigh the signals as advisory inputs,
  treat convergence as strengthening the case, and resolve and surface any conflict in its
  reasoning rather than silently following one block

#### Scenario: Reconciliation-aware prompt reads correctly with one or no signals

- **WHEN** a rebalance runs for a session frozen on the reconciliation-aware prompt version
  with at most one signal block attached
- **THEN** the prompt SHALL still read correctly, with nothing to reconcile, and the run
  SHALL proceed unchanged from attaching that one (or no) signal

#### Scenario: Older sessions receive no reconciliation section

- **WHEN** a rebalance runs for a session frozen on a prompt version predating the
  reconciliation-aware version
- **THEN** the agent SHALL be given the prompt without any reconciliation section, unchanged
  from that frozen version's behavior

#### Scenario: Reconciliation-aware prompt preserves the output contract

- **WHEN** the reconciliation-aware rebalance prompt is used for a run
- **THEN** the agent SHALL still return long-only target allocations summing to
  approximately 1.0, with an omitted or ~0-weight holding meaning exit, unchanged from the
  prior prompt version's output schema
