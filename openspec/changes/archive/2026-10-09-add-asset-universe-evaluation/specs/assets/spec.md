## ADDED Requirements

### Requirement: Generate and persist an AI evaluation of the asset universe

The system SHALL generate an AI-authored evaluation of the entire asset universe
and persist exactly one current evaluation. The evaluation SHALL be markdown
narrative plus bulleted key findings (strengths, concerns, and suggestions)
assessing diversification, sector/category concentration, quality, notable gaps,
and foreign or unpriceable listings. The persisted record SHALL include the
generated content, the time it was generated, and a fingerprint of the universe
captured at generation time. Generating a new evaluation SHALL replace the
previous record; no history is retained.

#### Scenario: Generate an evaluation

- **WHEN** an evaluation is generated for a non-empty universe
- **THEN** the system summarizes the universe (counts by category and sector,
  eligibility counts, concentration, and foreign/unpriceable listings), requests
  an AI narrative with bulleted findings, and stores the content together with the
  generation time and the universe fingerprint

#### Scenario: Only one current evaluation is kept

- **WHEN** an evaluation already exists and a new one is generated
- **THEN** the stored record (content, fingerprint, and generation time) is
  replaced by the new evaluation and no prior evaluation remains

#### Scenario: AI provider unavailable during generation

- **WHEN** generation is requested but the AI provider cannot be reached or returns
  no usable result
- **THEN** no evaluation is stored or replaced and the caller receives an error
  indicating the evaluation could not be generated

### Requirement: Lazy-fill the evaluation on first read

The system SHALL generate and persist the evaluation the first time it is read when
none exists yet, and SHALL return the stored evaluation without regenerating on
subsequent reads.

#### Scenario: First read with no evaluation

- **WHEN** the evaluation is read and none has ever been generated
- **THEN** the system generates one, persists it, and returns it

#### Scenario: Subsequent read returns the stored evaluation

- **WHEN** the evaluation is read and a current evaluation already exists
- **THEN** the system returns the stored evaluation without generating a new one

### Requirement: Flag the evaluation as outdated when the universe changes

On read, the system SHALL recompute a fingerprint over the current universe and
compare it to the fingerprint stored with the evaluation. The evaluation SHALL be
reported as outdated when the two fingerprints differ. The fingerprint SHALL be
derived from each asset's mutable attributes so that it changes when assets are
added or removed and when an existing asset's attributes change (including the
nightly metric refresh).

#### Scenario: Universe unchanged since generation

- **WHEN** the evaluation is read and no asset has changed since it was generated
- **THEN** the evaluation is reported as not outdated

#### Scenario: Asset added or removed since generation

- **WHEN** an asset has been added to or removed from the universe since the
  evaluation was generated
- **THEN** reading the evaluation reports it as outdated

#### Scenario: Existing asset changed since generation

- **WHEN** an existing asset's attributes have changed since the evaluation was
  generated (for example a metric refresh or eligibility change)
- **THEN** reading the evaluation reports it as outdated

### Requirement: Read and refresh the asset universe evaluation via the API

The system SHALL expose an endpoint to read the current evaluation — returning its
content, its generation time, and whether it is outdated — and an endpoint to
refresh (regenerate) it on demand. The read endpoint SHALL lazy-fill when no
evaluation exists; the refresh endpoint SHALL always regenerate and replace the
stored evaluation.

#### Scenario: Read the current evaluation

- **WHEN** a client requests the current evaluation
- **THEN** the response includes the narrative, the key findings, the generation
  time, and an outdated flag computed against the current universe

#### Scenario: Refresh the evaluation on request

- **WHEN** a client requests a refresh
- **THEN** the system regenerates the evaluation against the current universe,
  replaces the stored record, and returns the new evaluation reported as not
  outdated

#### Scenario: Read an empty universe

- **WHEN** the evaluation is read while the universe contains no assets
- **THEN** the system does not call the AI provider and the response indicates no
  evaluation is available
