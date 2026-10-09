## ADDED Requirements

### Requirement: Backfill the brokerage symbol for unverified assets

The system SHALL provide a one-off, re-runnable operation that resolves the brokerage's canonical symbol for existing assets that lack one (assets whose stored brokerage symbol is absent because they were added before add-time brokerage verification). For each such asset, the system SHALL look the asset up on the brokerage using the asset's category to determine its asset class, and SHALL store the brokerage's canonical symbol when the brokerage lists the asset as tradable. An asset the brokerage does not list, or lists as not tradable, SHALL be left without a brokerage symbol so it remains identifiable as not tradable. The operation SHALL be fail-open — a failure resolving one asset SHALL be recorded and skipped without aborting the rest — and SHALL be idempotent, so it may be re-run safely and only ever fills in assets still missing a symbol. The operation SHALL report how many assets it updated. The operation SHALL NOT alter assets that already have a brokerage symbol.

#### Scenario: Resolve a tradable legacy asset

- **WHEN** the backfill runs and an asset without a brokerage symbol is listed by the brokerage as tradable
- **THEN** the system SHALL store the brokerage's canonical symbol on that asset (even when it differs from the asset's ticker) and count it as updated

#### Scenario: Leave a genuinely untradable asset flagged

- **WHEN** the backfill runs and an asset without a brokerage symbol is not listed by the brokerage, or is listed as not tradable
- **THEN** the system SHALL leave that asset without a brokerage symbol so it remains identifiable as not tradable, and SHALL NOT count it as updated

#### Scenario: One asset's failure does not abort the pass

- **WHEN** the backfill runs and resolving one asset raises an error
- **THEN** the system SHALL record the failure, leave that asset without a brokerage symbol, and continue resolving the remaining assets

#### Scenario: Idempotent and non-destructive on re-run

- **WHEN** the backfill is run again after a previous run
- **THEN** the system SHALL only attempt assets still missing a brokerage symbol and SHALL NOT modify assets that already have one
