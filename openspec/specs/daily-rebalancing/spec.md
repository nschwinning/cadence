# daily-rebalancing Specification

## Purpose
Keeps AI-managed paper portfolios current by letting the AI re-evaluate holdings and place adjusting trades once per trading day, triggered automatically by a scheduled job, so a portfolio drifts with the AI's evolving view rather than being set once and forgotten.

## Requirements

### Requirement: Rebalance a session

The system SHALL rebalance a single active AI-managed session: read its current live positions and account summary, assemble candidate tickers from the current asset universe **restricted to the session's persisted asset scope** (stocks only, crypto only, or both — enriched with name, sector, category, and eligibility), and ask the AI — **using the session's persisted risk profile** (conservative, balanced, or aggressive), defaulting to balanced when none is persisted — to produce a set of long-only target allocations — fractions in [0, 1] that sum to approximately 1.0 — for the whole portfolio. Candidate tickers the session does not currently hold that are **currently quarantined for the session by a recent stop-loss** (their cooldown has not yet expired) SHALL be excluded from the candidate set presented to the AI, regardless of the trend opt-in, so that a just-stopped position is not immediately re-entered; a quarantine whose cooldown has expired SHALL no longer exclude its ticker; a ticker the session still holds SHALL NOT be excluded by a quarantine. The technical-indicator trend strategy SHALL be applied to the rebalance **only when the session opted into it** (the opt-in frozen at build time; a session with no persisted opt-in SHALL be treated as opted out). **When the session opted in**: candidate tickers the session does not currently hold SHALL be **hard-filtered by the deterministic trend gate** derived from each asset's latest stored technical-indicator snapshot — a candidate whose uptrend gate does not pass SHALL be dropped from the candidate set and SHALL NOT be presented to the AI, so that new positions are only ever entered in confirmed uptrends; a candidate that has no stored indicator snapshot (its trend cannot be established) SHALL be treated as failing the gate and dropped; the candidates that survive the gate SHALL be annotated with their trend indicators; and for each ticker the session currently holds, the system SHALL attach the holding's full indicator set and deterministic reversal flags to the AI's input and let the **AI decide** whether to sell, trim, or hold; holdings SHALL NOT be hard-exited by the trend gate. **When the session did not opt in**: no trend gate SHALL be applied — every in-scope candidate the session does not hold SHALL be presented to the AI without indicator annotations, and holdings SHALL NOT carry indicator or reversal context. **When the session opted into the risk guardrails** (the opt-in and parameters frozen at build time; a session with no persisted guardrail setting SHALL be treated as opted out), the AI SHALL be told the guardrail caps (maximum per asset, maximum per asset class, minimum number of positions, and maximum invested percentage) so it can plan within them. The AI MAY research and propose assets not currently in the universe (discovery is always enabled), which SHALL be added to the universe on a best-effort basis bounded by a configured maximum number of new assets per run; **a discovered asset whose category falls outside the session's asset scope SHALL be rejected — not added and not traded**, and — **only when the session opted into the trend strategy** — a discovered asset that does not pass the trend gate SHALL likewise be excluded from the candidate set presented to the AI. When a session has no persisted asset scope (for example a session built before this capability existed), the rebalance SHALL treat its scope as both. **When the session opted into the risk guardrails, the system SHALL deterministically enforce them on the AI's target-allocation vector before computing target share counts** so that no single ticker exceeds the maximum-per-asset cap, no asset class exceeds the maximum-per-class cap, and the total invested fraction does not exceed the maximum invested percentage (the remainder held as cash) — excess weight removed by a per-asset or per-class cap SHALL be redistributed proportionally to the tickers still below their caps, and when the caps cannot absorb the full capital the shortfall SHALL remain as cash; the deterministic enforcement is the guarantee and the caps given to the AI are advisory. The minimum-number-of-positions guardrail SHALL NOT be enforced by fabricating holdings the AI did not target: it is applied as the AI instruction above plus the diversification floor implied by the maximum-per-asset cap, and when the AI targets fewer holdings than the configured minimum the shortfall SHALL be recorded as a guardrail observation on the run rather than failing the rebalance. The system SHALL then re-weight the portfolio toward those (guardrail-enforced) targets: for each ticker it SHALL compare the currently held share count with the target share count implied by the allocation and the allocated capital, and apply the difference as a brokerage order — buying to increase a position, selling to reduce it, and fully selling any held position that is absent from the targets or given an allocation of ~0. Trivial fractional differences (less than one whole share) SHALL be skipped. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches. The rebalance SHALL be processed in the background and recorded as an AI-portfolio event and a session run.

#### Scenario: Rebalance applies AI decisions

- **WHEN** a rebalance runs for an active session
- **THEN** the system SHALL trade toward the AI's target allocations — buying under-weight holdings, selling over-weight holdings, and fully exiting holdings absent from the targets — record the trades and closed positions, update the portfolio's holdings to the resulting target set, and mark the event succeeded

#### Scenario: Rebalance honours the session's asset scope

- **WHEN** a rebalance runs for a session whose asset scope is stocks only (or crypto only)
- **THEN** the AI SHALL be given only universe assets whose category matches the scope, and any AI-discovered asset outside that scope SHALL be rejected rather than added or traded

#### Scenario: Rebalance applies the session's risk profile

- **WHEN** a rebalance runs for a session that was built with a non-default risk profile (for example aggressive or conservative)
- **THEN** the AI SHALL be asked to rebalance toward that persisted risk profile rather than a fixed default, and a session built before this behaviour existed (no persisted risk profile) SHALL be treated as balanced

#### Scenario: Rebalance enforces the session's frozen guardrails

- **WHEN** a rebalance runs for a session that was built with the risk guardrails enabled and the AI returns target allocations that exceed the maximum-per-asset cap, exceed the maximum-per-class cap, or would invest more than the maximum invested percentage
- **THEN** the system SHALL clamp and redistribute the target weights so no ticker exceeds the per-asset cap and no class exceeds the per-class cap, SHALL scale them so the invested fraction does not exceed the maximum invested percentage (holding the remainder as cash), and SHALL compute target share counts from the enforced weights

#### Scenario: Rebalance ignores guardrails when opted out

- **WHEN** a rebalance runs for a session that was not built with the risk guardrails (including a session built before the guardrails existed)
- **THEN** the system SHALL apply no allocation caps and SHALL trade toward the AI's target allocations unchanged by any guardrail

#### Scenario: Recently stopped tickers are excluded during cooldown

- **WHEN** a rebalance runs for a session that has a stop-loss quarantine whose cooldown has not yet expired, and the quarantined ticker is a candidate the session does not currently hold
- **THEN** the system SHALL exclude that ticker from the candidate set presented to the AI, so the AI cannot immediately re-buy the just-stopped position

#### Scenario: Expired quarantine no longer excludes a ticker

- **WHEN** a rebalance runs for a session whose stop-loss quarantine for a ticker has passed its cooldown expiry
- **THEN** the system SHALL present that ticker as an ordinary candidate again (subject to the usual scope and trend rules)

#### Scenario: Candidates are hard-filtered by the trend gate

- **WHEN** a rebalance runs for a session that opted into the technical-indicator trend strategy and assembles candidate tickers the session does not currently hold
- **THEN** the system SHALL drop every candidate whose latest indicator snapshot does not pass the uptrend gate (including candidates with no stored snapshot) and SHALL present only the surviving, trend-confirmed candidates — annotated with their trend indicators — to the AI

#### Scenario: Holdings carry trend context for AI-decided exits

- **WHEN** a rebalance runs for a session that opted in and assembles the session's current holdings
- **THEN** the system SHALL attach each holding's full indicator set and deterministic reversal flags to the AI's input and SHALL let the AI decide whether to sell, trim, or hold that position, without hard-exiting any holding on the trend gate

#### Scenario: Rebalance ignores technical indicators when opted out

- **WHEN** a rebalance runs for a session that did not opt into the trend strategy
- **THEN** the system SHALL NOT apply the trend gate to candidates and SHALL NOT attach indicator or reversal context to candidates or holdings, presenting every in-scope candidate the session does not hold to the AI without indicator annotations

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
