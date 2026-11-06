## ADDED Requirements

### Requirement: Market state in the overview

The dashboard overview SHALL report whether the US equity market is currently open as a boolean, derived from the broker market clock. The derivation SHALL be fault-tolerant: if the market-clock lookup fails or is unavailable for any reason, the overview SHALL fall back to a documented default (reported as open, matching the valuation layer's existing default-open convention) rather than failing, so the overview endpoint always succeeds. Reporting the market state SHALL NOT change how any session's value is computed: equities remain marked to their last official close when the market is closed, crypto remains priced live, strategy bots remain valued from their last stored observation, and the refetch cadence is unchanged. The dashboard SHALL display a corresponding market open/closed status label derived from this field.

#### Scenario: Market is open

- **WHEN** a client requests the dashboard overview while the equity market clock reports open
- **THEN** the overview SHALL report the market state as open
- **AND** the dashboard SHALL display a status label indicating the market is open

#### Scenario: Market is closed

- **WHEN** a client requests the dashboard overview while the equity market clock reports closed
- **THEN** the overview SHALL report the market state as closed
- **AND** the dashboard SHALL display a status label indicating the market is closed

#### Scenario: Market clock unavailable

- **WHEN** a client requests the dashboard overview and the market-clock lookup fails or is unavailable
- **THEN** the overview SHALL still be returned successfully with the documented default market state rather than returning an error
- **AND** the dashboard SHALL display a status label reflecting that default state

#### Scenario: Valuation behaviour is unaffected

- **WHEN** the overview reports the market as closed
- **THEN** each session's reported current value SHALL be computed exactly as it was before this field existed, with equities marked to their last official close, crypto priced live, and strategy bots valued from their last stored observation
