## MODIFIED Requirements

### Requirement: Enrollment in daily rebalancing

The system SHALL record, per session, its rebalance **cadence** — daily, weekly, or monthly — as its scheduling mode. A session is **enrolled** when it carries any of these three rebalancing cadences, and only enrolled, active sessions SHALL be picked up by the trigger. Every session created by an AI portfolio build SHALL be enrolled with the cadence chosen at build, defaulting to daily when none is chosen; the build SHALL NOT offer a way to disable rebalancing entirely. (The non-enrolled, manual scheduling mode remains a valid recorded state for sessions created by other means or before enrollment was mandatory.) A session with no persisted cadence (for example one built before this option existed) SHALL be treated as daily.

#### Scenario: Build enrolls a session

- **WHEN** an AI portfolio is built
- **THEN** the resulting session SHALL be enrolled for rebalancing, regardless of any client input, because the build offers no way to disable rebalancing

#### Scenario: Build freezes the chosen cadence

- **WHEN** an AI portfolio is built selecting weekly (or monthly) rebalancing
- **THEN** the resulting session SHALL be recorded with that cadence and every later automated rebalance for the session SHALL follow it

#### Scenario: Build defaults to daily cadence

- **WHEN** an AI portfolio is built without specifying a cadence
- **THEN** the resulting session SHALL be enrolled with daily rebalancing

### Requirement: Cron-guarded daily rebalance trigger

The system SHALL expose an endpoint that triggers a rebalance for every active session enrolled in **any** rebalancing cadence (daily, weekly, or monthly). For each such session the endpoint SHALL apply a per-session **calendar-boundary due-check** before starting its rebalance: a **daily** session is always due; a **weekly** session is due only on the first trigger run of a new ISO week (year, week), evaluated in the US market timezone (Eastern); a **monthly** session is due only on the first trigger run of a new calendar month (year, month), evaluated in the US market timezone (Eastern); and a session that has **never completed a rebalance** (never allocated) is due now regardless of cadence, so its opening allocation is not delayed by its cadence. The endpoint SHALL be protected by a shared-secret token supplied in a request header; a missing or incorrect token SHALL be rejected, and when the configured token is empty every request SHALL be rejected. The endpoint SHALL start the per-session rebalances in the background, skip sessions that already have a rebalance running, **skip sessions that are not yet ready for daily rebalancing because their initial build orders have not all filled (see "Defer a session until its build orders have filled")**, skip sessions whose cadence is **not yet due**, and return immediately with which sessions were triggered and which were skipped. **A session skipped because its build orders have not yet filled SHALL be reported as skipped, distinctly from a session skipped because a rebalance is already running, so its deferral is observable; such a session SHALL be picked up by a later trigger once its build orders have filled.** A session skipped only because it is **not yet due** SHALL be reported with a reason distinct from "already running" and "awaiting build fill", and SHALL be picked up on a later trigger once its period boundary is crossed.

#### Scenario: Valid token triggers all enrolled sessions

- **WHEN** the endpoint is called with the correct token
- **THEN** the system SHALL start a rebalance for each active enrolled session that is ready and due (skipping any already running, any whose build orders have not yet filled, and any not yet due) and respond with the triggered and skipped session ids

#### Scenario: Invalid or missing token

- **WHEN** the endpoint is called without a token or with an incorrect token, or the configured token is empty
- **THEN** the system SHALL reject the request and SHALL NOT start any rebalance

#### Scenario: Freshly-built session with unfilled build orders is skipped

- **WHEN** the endpoint is called and an active enrolled session's initial build orders have not all reached a terminal filled state
- **THEN** the system SHALL NOT start a rebalance for that session and SHALL report it among the skipped sessions

#### Scenario: Session included once its build orders fill

- **WHEN** the endpoint is called and an active enrolled session's initial build orders have all reached a terminal filled state
- **THEN** the system SHALL start a rebalance for that session (unless one is already running)

#### Scenario: Daily session is always due

- **WHEN** the endpoint is called and an active daily-cadence session is ready
- **THEN** the system SHALL start a rebalance for that session on every trigger run

#### Scenario: Weekly session rebalances once per ISO week

- **WHEN** the endpoint is called and an active weekly-cadence session has already completed a rebalance earlier in the current ISO week
- **THEN** the system SHALL skip that session as not yet due; **AND WHEN** the endpoint is called on the first trigger run of the next ISO week, the system SHALL start a rebalance for that session

#### Scenario: Monthly session rebalances once per calendar month

- **WHEN** the endpoint is called and an active monthly-cadence session has already completed a rebalance earlier in the current calendar month
- **THEN** the system SHALL skip that session as not yet due; **AND WHEN** the endpoint is called on the first trigger run of the next calendar month, the system SHALL start a rebalance for that session

#### Scenario: Never-allocated session is due regardless of cadence

- **WHEN** the endpoint is called and an active weekly- or monthly-cadence session has never been allocated (has no completed rebalance)
- **THEN** the system SHALL treat the session as due and start its opening allocation on the next trigger run rather than waiting for a period boundary

#### Scenario: Not-yet-due session reported distinctly

- **WHEN** the endpoint skips a session only because its cadence is not yet due
- **THEN** the system SHALL report it under a skip reason separate from "already running" and "awaiting build fill"

### Requirement: Cron-guarded weekend crypto-only rebalance trigger

The system SHALL expose an endpoint, separate from the daily rebalance trigger, that
starts a **crypto-only** rebalance for every active **daily-cadence** session enrolled
in rebalancing. Weekly- and monthly-cadence sessions SHALL NOT be tended by this
weekend crypto trigger, so a mixed stock+crypto weekly- or monthly-cadence session is
rebalanced as a whole exactly once per period on a weekday run rather than having its
crypto sleeve rebalanced separately on the weekend. The endpoint SHALL be protected by
the same shared-secret token as the daily trigger supplied in a request header; a
missing or incorrect token SHALL be rejected, and when the configured token is empty
every request SHALL be rejected. The endpoint SHALL start the per-session crypto-only
rebalances in the background, skip sessions that already have a rebalance running, skip
sessions that are not yet ready because their initial build orders have not all filled
(see "Defer a session until its build orders have filled"), and **skip, without
invoking the agent, any session that neither holds nor targets any crypto**. It SHALL
return immediately with which sessions were triggered and which were skipped,
distinguishing the skip reasons (already running, awaiting build fill, or no crypto to
rebalance).

This trigger is intended to be scheduled on days the weekday daily trigger does not
run (weekends), so that crypto — which trades around the clock — is still rebalanced
on those days while equities are left untouched. The scheduling cadence itself is a
deployment concern (the cron schedule), not enforced by this endpoint; the endpoint
SHALL perform a crypto-only rebalance whenever it is validly called.

#### Scenario: Valid token triggers crypto-only rebalances

- **WHEN** the endpoint is called with the correct token
- **THEN** the system SHALL start a crypto-only rebalance for each active
  daily-cadence session that is ready and involves crypto, and respond with the
  triggered and skipped session ids

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

#### Scenario: Weekly or monthly session is not tended on the weekend

- **WHEN** the endpoint is called and an active session's cadence is weekly or monthly
- **THEN** the system SHALL NOT start a crypto-only rebalance for that session
