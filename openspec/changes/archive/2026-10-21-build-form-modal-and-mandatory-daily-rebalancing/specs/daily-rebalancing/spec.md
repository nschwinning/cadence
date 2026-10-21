## MODIFIED Requirements

### Requirement: Enrollment in daily rebalancing

The system SHALL record, per session, whether it is enrolled in daily rebalancing (a scheduling mode). Only enrolled, active sessions SHALL be picked up by the daily trigger. Every session created by an AI portfolio build SHALL be enrolled in daily rebalancing; the build SHALL NOT offer an opt-out. (The non-enrolled, manual scheduling mode remains a valid recorded state for sessions created by other means or before enrollment was mandatory.)

#### Scenario: Build enrolls a session

- **WHEN** an AI portfolio is built
- **THEN** the resulting session SHALL be enrolled for daily rebalancing, regardless of any client input, because the build offers no opt-out
