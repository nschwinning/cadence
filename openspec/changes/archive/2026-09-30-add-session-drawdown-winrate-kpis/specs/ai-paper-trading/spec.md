## ADDED Requirements

### Requirement: Session risk and trade-effectiveness KPIs

The per-session KPI read SHALL additionally report a session's maximum drawdown, win rate, average win, average loss, best trade, and worst trade, each computed on read from data already recorded for the session and reported as absent (null) when its inputs are insufficient.

**Maximum drawdown** SHALL be the largest peak-to-trough decline in the session's portfolio value, expressed as a non-negative fraction of the running peak, computed over the session's daily value-snapshot series ordered by date: tracking the running maximum value and the deepest proportional drop below it. It SHALL be reported as absent when the session has no value snapshots, and SHALL be zero when the value series only ever rose (never declined below a prior peak).

**Win rate** SHALL be the fraction of the session's closed positions whose realized profit-and-loss is strictly greater than zero, expressed in [0, 1]. It SHALL be reported as absent when the session has no closed positions.

**Average win** SHALL be the mean realized profit-and-loss of the session's closed positions with realized P&L strictly greater than zero, and **average loss** SHALL be the mean realized profit-and-loss of the session's closed positions with realized P&L strictly less than zero. Average win SHALL be reported as absent when the session has no winning closed positions; average loss SHALL be reported as absent when it has no losing closed positions.

**Best trade** SHALL be the maximum, and **worst trade** the minimum, realized profit-and-loss across the session's closed positions. Both SHALL be reported as absent when the session has no closed positions.

These figures SHALL NOT change how value snapshots or closed positions are recorded, and SHALL require no new stored fields.

#### Scenario: Maximum drawdown from the value series

- **WHEN** the KPIs are read for a session whose daily value snapshots rise to a peak and then decline before partially recovering
- **THEN** the read SHALL report the maximum drawdown as the deepest peak-to-trough decline expressed as a fraction of the running peak

#### Scenario: Drawdown is zero for a monotonically rising series

- **WHEN** the KPIs are read for a session whose value snapshots never fall below a prior peak
- **THEN** the read SHALL report a maximum drawdown of zero

#### Scenario: Drawdown absent without snapshots

- **WHEN** the KPIs are read for a session that has no value snapshots
- **THEN** the read SHALL report the maximum drawdown as absent

#### Scenario: Win rate and trade averages from closed positions

- **WHEN** the KPIs are read for a session with a mix of winning and losing closed positions
- **THEN** the read SHALL report the win rate as the fraction of closed positions with realized P&L above zero, the average win as the mean realized P&L of the winners, the average loss as the mean realized P&L of the losers, the best trade as the maximum realized P&L, and the worst trade as the minimum realized P&L

#### Scenario: Trade metrics absent without closed positions

- **WHEN** the KPIs are read for a session that has no closed positions
- **THEN** the read SHALL report win rate, average win, average loss, best trade, and worst trade all as absent

#### Scenario: Average win or average loss absent when one side is empty

- **WHEN** the KPIs are read for a session whose closed positions are all winners (or all losers)
- **THEN** the read SHALL report a win rate and the populated side's average, and SHALL report the empty side's average (average loss when all winners, or average win when all losers) as absent
