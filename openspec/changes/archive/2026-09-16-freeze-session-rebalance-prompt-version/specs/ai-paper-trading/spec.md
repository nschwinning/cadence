## MODIFIED Requirements

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
version. Each AI-managed paper-trading session SHALL **freeze** a rebalance prompt
version: when the session is built, the version that is active at that time SHALL
be captured and stored on the session as a required (non-nullable) value, and
every subsequent rebalance for that session SHALL use that frozen version — not
whatever is active later — so that adding a newer prompt version does not change
the behavior of sessions already built. Existing sessions that predate per-session
freezing SHALL be migrated to the highest prompt version that exists at migration
time, so that every session has a frozen version and no runtime fallback is
required. When a rebalance runs, the system SHALL load the session's frozen prompt
version, fill its placeholders with the run's values, and use the result as the
agent's instructions and input; the rendered values SHALL be identical to those
produced by the previously hardcoded prompt for the same inputs. If the frozen
prompt version cannot be found in the database, the rebalance SHALL fail with a
clear error rather than running against an empty prompt.

The initial deploy SHALL seed version 1 with the prompt text that is in use at
the time versioning was introduced, so that behavior is unchanged on first run.
Adding a new prompt version (a new record with a higher version) SHALL change the
prompt used by sessions built **after** it becomes active, without any code
change, while leaving already-built sessions on their frozen version. The frozen
version SHALL be observable on the session's read model. This requirement covers
the rebalance prompt only; the AI build prompt is unaffected.

#### Scenario: A session freezes the active version at build time

- **WHEN** an AI build creates a paper-trading session and version N is the active
  rebalance prompt
- **THEN** the system SHALL store N as the session's frozen rebalance prompt
  version
- **AND** the frozen version SHALL be readable on the session's read model

#### Scenario: Rebalance uses the session's frozen version

- **WHEN** an AI rebalance runs for a session whose frozen prompt version is N
- **AND** newer prompt versions exist
- **THEN** the system SHALL use version N as the rebalance prompt
- **AND** SHALL fill its placeholders with the run's risk profile, holdings,
  account summary, and candidate universe before invoking the agent

#### Scenario: Rebalance uses the active (highest-version) prompt

- **WHEN** existing sessions are migrated to per-session freezing
- **THEN** each session SHALL be frozen to the highest prompt version that exists
  at migration time
- **AND** subsequent rebalances for those sessions SHALL use that frozen version

#### Scenario: A newer version supersedes the previous prompt

- **WHEN** a new prompt record is added with a version higher than the current
  active version
- **THEN** sessions built after it becomes active SHALL freeze and use the new
  record's instructions and input template
- **AND** sessions already built SHALL keep using their frozen version
- **AND** the previous version SHALL remain stored and unchanged

#### Scenario: Seeded first version preserves current behavior

- **WHEN** prompt versioning is first deployed and no prompt has been edited
- **THEN** the active prompt SHALL be the seeded version 1
- **AND** the instructions and input it produces for a given run SHALL match the
  text the previously hardcoded prompt produced for the same inputs

#### Scenario: No prompt available

- **WHEN** an AI rebalance runs and the session's frozen prompt version cannot be
  found in the database
- **THEN** the system SHALL fail the rebalance with an explicit error indicating
  the rebalance prompt is missing
- **AND** SHALL NOT invoke the agent with an empty prompt
