## ADDED Requirements

### Requirement: Cron-guarded weekend crypto-only rebalance trigger

The system SHALL expose an endpoint, separate from the daily rebalance trigger, that
starts a **crypto-only** rebalance for every active session enrolled in daily
rebalancing. The endpoint SHALL be protected by the same shared-secret token as the
daily trigger supplied in a request header; a missing or incorrect token SHALL be
rejected, and when the configured token is empty every request SHALL be rejected. The
endpoint SHALL start the per-session crypto-only rebalances in the background, skip
sessions that already have a rebalance running, skip sessions that are not yet ready
because their initial build orders have not all filled (see "Defer a session until
its build orders have filled"), and **skip, without invoking the agent, any session
that neither holds nor targets any crypto**. It SHALL return immediately with which
sessions were triggered and which were skipped, distinguishing the skip reasons
(already running, awaiting build fill, or no crypto to rebalance).

This trigger is intended to be scheduled on days the weekday daily trigger does not
run (weekends), so that crypto — which trades around the clock — is still rebalanced
on those days while equities are left untouched. The scheduling cadence itself is a
deployment concern (the cron schedule), not enforced by this endpoint; the endpoint
SHALL perform a crypto-only rebalance whenever it is validly called.

#### Scenario: Valid token triggers crypto-only rebalances

- **WHEN** the endpoint is called with the correct token
- **THEN** the system SHALL start a crypto-only rebalance for each active enrolled
  session that is ready and involves crypto, and respond with the triggered and
  skipped session ids

#### Scenario: Invalid or missing token

- **WHEN** the endpoint is called without a token or with an incorrect token, or the
  configured token is empty
- **THEN** the system SHALL reject the request and SHALL NOT start any rebalance

#### Scenario: Session with no crypto is skipped without the agent

- **WHEN** the endpoint is called and an active enrolled session neither holds nor
  targets any crypto asset
- **THEN** the system SHALL NOT start a rebalance for that session, SHALL NOT invoke
  the AI agent for it, and SHALL report it among the skipped sessions with a reason
  distinguishing it from sessions skipped for already running or awaiting build fill

#### Scenario: Freshly-built session with unfilled build orders is skipped

- **WHEN** the endpoint is called and an active enrolled session's initial build
  orders have not all reached a terminal filled state
- **THEN** the system SHALL NOT start a rebalance for that session and SHALL report it
  among the skipped sessions

#### Scenario: Already-running session is skipped

- **WHEN** the endpoint is called and a session already has a rebalance running
- **THEN** the system SHALL NOT start a second rebalance for that session and SHALL
  report it as skipped for already running
