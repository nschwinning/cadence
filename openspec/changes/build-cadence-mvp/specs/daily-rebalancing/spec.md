## Purpose

Keeps AI-managed paper portfolios current by letting the AI re-evaluate holdings and place adjusting trades once per trading day, triggered automatically by a scheduled job, so a portfolio drifts with the AI's evolving view rather than being set once and forgotten.

## ADDED Requirements

### Requirement: Rebalance a session

The system SHALL rebalance a single active AI-managed session: read its current live positions and account summary, assemble candidate tickers, ask the AI to evaluate each existing holding (hold, sell, or cover) and optionally propose new positions, and then apply the resulting deltas as brokerage orders. Closing trades SHALL be executed before opening trades, and opening trades SHALL be sized against available buying power. The rebalance SHALL be processed in the background and recorded as an AI-portfolio event and a session run.

#### Scenario: Rebalance applies AI decisions

- **WHEN** a rebalance runs for an active session
- **THEN** the system SHALL close positions the AI marks sell/cover, open the AI's new positions within available buying power, record the trades and closed positions, and mark the event succeeded

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
