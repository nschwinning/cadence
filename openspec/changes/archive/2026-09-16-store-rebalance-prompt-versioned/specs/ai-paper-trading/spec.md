## ADDED Requirements

### Requirement: Versioned rebalancing prompt stored in the database

The AI rebalance flow SHALL obtain its prompt from a versioned prompt record
persisted in the database rather than from a value hardcoded in application code.
A prompt record SHALL comprise two parts: the agent **instructions** (the system
persona and requirements) and the run **input template** (the per-run message the
agent is given), each stored as a text template that preserves the runtime
placeholders the flow fills in (the reasoning/discovery caps in the instructions;
the risk profile, current holdings, account summary, and candidate universe in
the input template).

Prompt records SHALL be append-only and identified by a monotonically increasing
integer version. The **active** prompt SHALL be the record with the highest
version. When a rebalance runs, the system SHALL load the active prompt, fill its
placeholders with the run's values, and use the result as the agent's
instructions and input; the rendered values SHALL be identical to those produced
by the previously hardcoded prompt for the same inputs. If no prompt record
exists, the rebalance SHALL fail with a clear error rather than running against an
empty prompt.

The initial deploy SHALL seed version 1 with the prompt text that is in use at
the time of this change, so that behavior is unchanged on first run. Adding a new
prompt version (a new record with a higher version) SHALL change the prompt used
by subsequent rebalances without any code change. This requirement covers the
rebalance prompt only; the AI build prompt is unaffected.

#### Scenario: Rebalance uses the active (highest-version) prompt

- **WHEN** an AI rebalance runs and multiple prompt versions exist
- **THEN** the system SHALL use the record with the highest version as the
  rebalance prompt
- **AND** SHALL fill its placeholders with the run's risk profile, holdings,
  account summary, and candidate universe before invoking the agent

#### Scenario: Seeded first version preserves current behavior

- **WHEN** the change is first deployed and no prompt has been edited
- **THEN** the active prompt SHALL be the seeded version 1
- **AND** the instructions and input it produces for a given run SHALL match the
  text the previously hardcoded prompt produced for the same inputs

#### Scenario: A newer version supersedes the previous prompt

- **WHEN** a new prompt record is added with a version higher than the current
  active version
- **THEN** subsequent rebalances SHALL use the new record's instructions and
  input template
- **AND** the previous version SHALL remain stored and unchanged

#### Scenario: No prompt available

- **WHEN** an AI rebalance runs and no prompt record exists in the database
- **THEN** the system SHALL fail the rebalance with an explicit error indicating
  the rebalance prompt is missing
- **AND** SHALL NOT invoke the agent with an empty prompt
