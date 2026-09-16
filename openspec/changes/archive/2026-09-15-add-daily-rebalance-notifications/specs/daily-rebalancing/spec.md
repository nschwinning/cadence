## ADDED Requirements

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
