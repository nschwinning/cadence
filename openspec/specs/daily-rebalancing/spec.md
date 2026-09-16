# daily-rebalancing Specification

## Purpose
Keeps AI-managed paper portfolios current by letting the AI re-evaluate holdings and place adjusting trades once per trading day, triggered automatically by a scheduled job, so a portfolio drifts with the AI's evolving view rather than being set once and forgotten.

## Requirements

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

### Requirement: Enrollment in daily rebalancing

The system SHALL record, per session, whether it is enrolled in daily rebalancing (a scheduling mode). Only enrolled, active sessions SHALL be picked up by the daily trigger.

#### Scenario: Build enrolls a session

- **WHEN** an AI portfolio is built with daily rebalancing requested
- **THEN** the resulting session SHALL be marked for daily rebalancing

### Requirement: Cron-guarded daily rebalance trigger

The system SHALL expose an endpoint that triggers a rebalance for every active session enrolled in daily rebalancing. The endpoint SHALL be protected by a shared-secret token supplied in a request header; a missing or incorrect token SHALL be rejected, and when the configured token is empty every request SHALL be rejected. The endpoint SHALL start the per-session rebalances in the background, skip sessions that already have a rebalance running, and return immediately with which sessions were triggered and which were skipped.

#### Scenario: Valid token triggers all enrolled sessions

- **WHEN** the endpoint is called with the correct token
- **THEN** the system SHALL start a rebalance for each active enrolled session (skipping any already running) and respond with the triggered and skipped session ids

#### Scenario: Invalid or missing token

- **WHEN** the endpoint is called without a token or with an incorrect token, or the configured token is empty
- **THEN** the system SHALL reject the request and SHALL NOT start any rebalance

### Requirement: Execution guarded by market status

The system SHALL only place rebalance orders when the market is open, so that market orders are not sent into a closed market.

#### Scenario: Market closed

- **WHEN** a scheduled rebalance fires while the market is closed
- **THEN** the system SHALL not place orders and SHALL record the run as skipped

### Requirement: Notify on daily rebalance outcomes

The system SHALL send a push notification reporting the outcome of a daily (cron-triggered) rebalance for a session. A notification SHALL be sent when a daily rebalance submits one or more orders, summarizing at least the portfolio, the number of orders submitted, and each submitted order's side (buy/sell) and ticker. A notification SHALL also be sent when a daily rebalance fails, including a brief failure reason. The system SHALL NOT send a notification when a daily rebalance is skipped (for example the market is closed and nothing is tradable) or completes without submitting any order. Manually-triggered rebalances SHALL NOT send notifications. Notification delivery SHALL be best-effort: a failure to send a notification SHALL be logged and SHALL NOT change the rebalance outcome or the recorded event or run. When push-notification credentials are not configured, notifications SHALL be silently disabled and the rebalance SHALL proceed normally.

#### Scenario: Orders submitted by the daily job

- **WHEN** a daily rebalance submits one or more orders for a session
- **THEN** the system SHALL send a push notification summarizing the portfolio, the number of orders, and each order's side and ticker

#### Scenario: Daily job fails

- **WHEN** a daily rebalance run fails with an error
- **THEN** the system SHALL send a push notification including a brief failure reason

#### Scenario: Daily job skips or submits no orders

- **WHEN** a daily rebalance is skipped (market closed with nothing tradable) or completes without submitting any order
- **THEN** the system SHALL NOT send a notification

#### Scenario: Manual rebalance is not notified

- **WHEN** a rebalance is triggered manually (not by the daily cron job)
- **THEN** the system SHALL NOT send a notification, regardless of orders submitted or failure

#### Scenario: Notification delivery fails

- **WHEN** sending a notification fails (transport error or non-configured credentials)
- **THEN** the system SHALL log the condition and SHALL complete the rebalance and record its event and run exactly as if notification had not been attempted
