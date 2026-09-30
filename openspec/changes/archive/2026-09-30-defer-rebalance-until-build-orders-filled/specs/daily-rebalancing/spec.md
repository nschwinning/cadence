## ADDED Requirements

### Requirement: Defer a session until its build orders have filled

The system SHALL treat a freshly-built AI-managed session as **not yet ready for daily rebalancing** until the broker orders placed by its initial build have all reached a terminal filled/settled state, and SHALL treat it as ready once they have. Readiness SHALL be determined from the **actual broker fill status** of the session's initial build orders — not from an elapsed-run count, a wall-clock delay, or the optimistic local ledger. Before deciding readiness the system SHALL refresh those build orders' statuses against the broker (reconciling their recorded status with the broker's current order state), because the separate order-reconciliation trigger is not guaranteed to have run first. A session whose initial build placed **no orders that need to settle** — an all-cash build, or a build whose orders have already reached a terminal filled state (for example under an immediate-fill broker) — SHALL be considered ready immediately, so that this readiness gate never permanently strands a session. A build order that reached a terminal non-filled state (for example cancelled or rejected) SHALL NOT keep the session deferred, since it will never fill. This readiness gate governs only the automatic daily rebalance trigger; it SHALL NOT block a manually-requested single-session rebalance.

#### Scenario: Build orders still unfilled

- **WHEN** readiness is evaluated for a session whose initial build orders are still in a non-terminal state (for example placed while the market was closed and still submitted/pending at the broker)
- **THEN** the system SHALL report the session as not yet ready for daily rebalancing

#### Scenario: Build orders have filled

- **WHEN** readiness is evaluated for a session whose initial build orders have all reached a terminal filled state (confirmed against the broker)
- **THEN** the system SHALL report the session as ready for daily rebalancing

#### Scenario: No build orders to wait on

- **WHEN** readiness is evaluated for a session whose initial build placed no orders that need to settle (an all-cash build, or one whose orders already filled — for example under an immediate-fill broker)
- **THEN** the system SHALL report the session as ready immediately

#### Scenario: Terminal non-filled build order does not strand the session

- **WHEN** readiness is evaluated for a session whose initial build orders have all reached a terminal state, some filled and any remainder cancelled or rejected
- **THEN** the system SHALL NOT keep the session deferred on account of the non-filled orders and SHALL report it as ready

#### Scenario: Manual rebalance is not deferred

- **WHEN** a rebalance is requested manually for a session whose initial build orders have not yet filled
- **THEN** the readiness gate SHALL NOT block the manual rebalance

## MODIFIED Requirements

### Requirement: Cron-guarded daily rebalance trigger

The system SHALL expose an endpoint that triggers a rebalance for every active session enrolled in daily rebalancing. The endpoint SHALL be protected by a shared-secret token supplied in a request header; a missing or incorrect token SHALL be rejected, and when the configured token is empty every request SHALL be rejected. The endpoint SHALL start the per-session rebalances in the background, skip sessions that already have a rebalance running, **skip sessions that are not yet ready for daily rebalancing because their initial build orders have not all filled (see "Defer a session until its build orders have filled")**, and return immediately with which sessions were triggered and which were skipped. **A session skipped because its build orders have not yet filled SHALL be reported as skipped, distinctly from a session skipped because a rebalance is already running, so its deferral is observable; such a session SHALL be picked up by a later trigger once its build orders have filled.**

#### Scenario: Valid token triggers all enrolled sessions

- **WHEN** the endpoint is called with the correct token
- **THEN** the system SHALL start a rebalance for each active enrolled session that is ready (skipping any already running and any whose build orders have not yet filled) and respond with the triggered and skipped session ids

#### Scenario: Invalid or missing token

- **WHEN** the endpoint is called without a token or with an incorrect token, or the configured token is empty
- **THEN** the system SHALL reject the request and SHALL NOT start any rebalance

#### Scenario: Freshly-built session with unfilled build orders is skipped

- **WHEN** the endpoint is called and an active enrolled session's initial build orders have not all reached a terminal filled state
- **THEN** the system SHALL NOT start a rebalance for that session and SHALL report it among the skipped sessions

#### Scenario: Session included once its build orders fill

- **WHEN** the endpoint is called and an active enrolled session's initial build orders have all reached a terminal filled state
- **THEN** the system SHALL start a rebalance for that session (unless one is already running)
