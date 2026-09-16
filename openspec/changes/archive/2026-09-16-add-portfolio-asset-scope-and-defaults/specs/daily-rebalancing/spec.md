## MODIFIED Requirements

### Requirement: Rebalance a session

The system SHALL rebalance a single active AI-managed session: read its current live positions and account summary, assemble candidate tickers from the current asset universe **restricted to the session's persisted asset scope** (stocks only, crypto only, or both — enriched with name, sector, category, and eligibility), and ask the AI — **using the session's persisted risk profile** (conservative, balanced, or aggressive), defaulting to balanced when none is persisted — to produce a set of long-only target allocations — fractions in [0, 1] that sum to approximately 1.0 — for the whole portfolio. The AI MAY research and propose assets not currently in the universe (discovery is always enabled), which SHALL be added to the universe on a best-effort basis bounded by a configured maximum number of new assets per run; **a discovered asset whose category falls outside the session's asset scope SHALL be rejected — not added and not traded**. When a session has no persisted asset scope (for example a session built before this capability existed), the rebalance SHALL treat its scope as both. The system SHALL then re-weight the portfolio toward those targets: for each ticker it SHALL compare the currently held share count with the target share count implied by the allocation and the allocated capital, and apply the difference as a brokerage order — buying to increase a position, selling to reduce it, and fully selling any held position that is absent from the targets or given an allocation of ~0. Trivial fractional differences (less than one whole share) SHALL be skipped. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches. The rebalance SHALL be processed in the background and recorded as an AI-portfolio event and a session run.

#### Scenario: Rebalance applies AI decisions

- **WHEN** a rebalance runs for an active session
- **THEN** the system SHALL trade toward the AI's target allocations — buying under-weight holdings, selling over-weight holdings, and fully exiting holdings absent from the targets — record the trades and closed positions, update the portfolio's holdings to the resulting target set, and mark the event succeeded

#### Scenario: Rebalance honours the session's asset scope

- **WHEN** a rebalance runs for a session whose asset scope is stocks only (or crypto only)
- **THEN** the AI SHALL be given only universe assets whose category matches the scope, and any AI-discovered asset outside that scope SHALL be rejected rather than added or traded

#### Scenario: Rebalance applies the session's risk profile

- **WHEN** a rebalance runs for a session that was built with a non-default risk profile (for example aggressive or conservative)
- **THEN** the AI SHALL be asked to rebalance toward that persisted risk profile rather than a fixed default, and a session built before this behaviour existed (no persisted risk profile) SHALL be treated as balanced

#### Scenario: Session not eligible

- **WHEN** a rebalance is requested for a session that is not an active AI-managed session
- **THEN** the system SHALL reject the request

#### Scenario: A rebalance is already running for the session

- **WHEN** a rebalance is requested while one is already running for that session
- **THEN** the system SHALL skip starting a second concurrent rebalance for that session
