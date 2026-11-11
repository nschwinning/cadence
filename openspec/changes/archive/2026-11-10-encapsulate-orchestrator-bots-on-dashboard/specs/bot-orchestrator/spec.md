## ADDED Requirements

### Requirement: Orchestrator on the dashboard

Each active bot orchestrator SHALL appear on the dashboard as **one** performance row of kind
orchestrator, labelled with the orchestrator's label, covering its free capital and all of
its bots; the bots it deployed SHALL NOT appear as rows of their own. The row's figures SHALL
be computed as the dashboard's per-session performance requirement defines for orchestrators.
Stopped and archived orchestrators SHALL NOT appear, like stopped bots and closed sessions.

#### Scenario: One dashboard row per active orchestrator

- **WHEN** the dashboard loads with one active orchestrator running two bots
- **THEN** it SHALL show a single orchestrator row labelled with the orchestrator's label

#### Scenario: Stopped orchestrator leaves the dashboard

- **WHEN** an orchestrator is stopped
- **THEN** neither it nor its bots SHALL appear as dashboard rows
