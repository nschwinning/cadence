## ADDED Requirements

### Requirement: Intraday value-point capture at each tick

In addition to the daily value snapshot, the system SHALL persist a timestamped
intraday value point for every active bot session it processes on a tick, capturing the
session's total value — **cash plus the marked-to-market value of all open positions** —
and its aggregated realised and unrealised profit/loss at that tick's time. Capture is
forward-only: the system SHALL NOT reconstruct intraday points for ticks that happened
before this capability existed. When a tick processes no sessions (for example the
market is closed), the system SHALL record no intraday points. Capture failures SHALL
NOT be introduced into the trading path in a way that changes position or ledger
outcomes.

#### Scenario: Intraday point recorded per processed session

- **WHEN** a tick processes an active bot session during market hours
- **THEN** the system SHALL persist an intraday value point for that session stamped
  with the tick time, holding the session's total value (cash plus marked positions) and
  aggregated realised/unrealised profit/loss

#### Scenario: No points when nothing is processed

- **WHEN** a tick runs while the market is closed and processes no sessions
- **THEN** the system SHALL record no intraday value points

### Requirement: Intraday value-point retention

The system SHALL retain raw intraday value points for a bounded window of the most recent
30 days and SHALL prune points older than that window, so intraday storage does not grow
without limit. Pruning SHALL run as part of the once-daily snapshot job. Because the
`5min` and `hourly` resolutions are served from these raw points, both SHALL be bounded to
roughly this 30-day window; the `daily` and `monthly` resolutions are served from daily
snapshots and SHALL remain unbounded.

#### Scenario: Points older than the retention window are pruned

- **WHEN** the daily snapshot job runs
- **THEN** the system SHALL delete intraday value points older than the 30-day retention
  window and SHALL keep points within it

#### Scenario: Coarse resolutions are unaffected by intraday pruning

- **WHEN** intraday points older than 30 days have been pruned
- **THEN** the `daily` and `monthly` value-history resolutions SHALL still return the full
  recorded history from the daily snapshots

### Requirement: Multi-resolution value-history reads

The value-history read SHALL accept a resolution selector with the values `5min`,
`hourly`, `daily`, and `monthly`, and SHALL return the session's value series at the
requested resolution as points on a single uniform timestamped shape so one renderer can
display any resolution. `5min` SHALL return the raw intraday value points; `hourly` SHALL
downsample the intraday points to the last point within each clock hour; `daily` SHALL
return the recorded daily snapshots; `monthly` SHALL return the last recorded daily
snapshot within each calendar month. Each point SHALL carry its timestamp and total
value (and the realised/unrealised figures already exposed). The response SHALL indicate
which resolution it represents. An unrecognised resolution SHALL yield `422`; an unknown
session SHALL yield `404`. When the requested resolution has no data yet, the system
SHALL return an empty series rather than an error.

#### Scenario: Five-minute resolution returns intraday points

- **WHEN** a client requests a known session's value history at `5min` resolution
- **THEN** the system SHALL return the session's intraday value points, each with its
  timestamp and total value, oldest first

#### Scenario: Hourly resolution downsamples intraday points

- **WHEN** a client requests `hourly` resolution for a session with multiple intraday
  points inside the same clock hour
- **THEN** the system SHALL return one point per hour — the last point within each hour —
  each stamped with its timestamp and total value

#### Scenario: Daily and monthly resolutions use recorded snapshots

- **WHEN** a client requests `daily` or `monthly` resolution
- **THEN** the system SHALL return the daily snapshots (for `daily`) or the last daily
  snapshot per calendar month (for `monthly`), on the same timestamped point shape

#### Scenario: Unknown resolution is rejected

- **WHEN** a client requests value history with a resolution other than `5min`,
  `hourly`, `daily`, or `monthly`
- **THEN** the system SHALL respond with `422`

#### Scenario: Resolution with no data returns an empty series

- **WHEN** a client requests a resolution for which the session has no points yet (for
  example `5min` on a session created before intraday capture and not yet re-ticked)
- **THEN** the system SHALL return an empty series with the requested resolution, not an
  error
