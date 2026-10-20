## MODIFIED Requirements

### Requirement: Generate and persist an AI evaluation of the asset universe

The system SHALL generate an AI-authored evaluation of the entire asset universe
and persist exactly one current evaluation. The evaluation SHALL be markdown
narrative plus bulleted key findings (strengths, concerns, and suggestions)
assessing diversification, sector/category concentration, quality, notable gaps,
and foreign or unpriceable listings. The persisted record SHALL include the
generated content, the time it was generated, and a fingerprint of the universe
captured at generation time. Generating a new evaluation SHALL replace the
previous record; no history is retained.

The prompt given to the AI SHALL include the universe's current roster of
holdings grouped by sector, with each holding identified by its ticker and name,
ineligible holdings flagged, and crypto grouped as its own section, so the AI
knows exactly which assets are already present. The evaluation's suggestions
SHALL NOT recommend adding any asset that is already in the universe; suggested
additions SHALL name only tickers absent from the provided roster.

The evaluation SHALL respect Cadence's supported trading scope: the universe may
only contain US Alpaca-tradable individual equities and crypto, managed long-only
with full-universe weight allocation (no shorting, leverage, options, or
derivatives), and SHALL NOT hold ETFs, mutual funds, bond funds, fixed-income
instruments, cash-equivalent or money-market funds, or foreign (non-US-listed)
securities. The evaluation's suggestions SHALL stay within that scope — for
example adding specific individual stocks or crypto, reducing concentration,
addressing quality or sector gaps, or resolving foreign/unpriceable listings to
their US listing or ADR — and SHALL NOT recommend any instrument class Cadence
does not support.

#### Scenario: Generate an evaluation

- **WHEN** an evaluation is generated for a non-empty universe
- **THEN** the system summarizes the universe (counts by category and sector,
  eligibility counts, concentration, foreign/unpriceable listings, and the
  sector-grouped roster of holdings), requests an AI narrative with bulleted
  findings, and stores the content together with the generation time and the
  universe fingerprint

#### Scenario: Only one current evaluation is kept

- **WHEN** an evaluation already exists and a new one is generated
- **THEN** the stored record (content, fingerprint, and generation time) is
  replaced by the new evaluation and no prior evaluation remains

#### Scenario: AI provider unavailable during generation

- **WHEN** generation is requested but the AI provider cannot be reached or returns
  no usable result
- **THEN** no evaluation is stored or replaced and the caller receives an error
  indicating the evaluation could not be generated

#### Scenario: Suggestions stay within the supported scope

- **WHEN** an evaluation is generated
- **THEN** the prompt given to the AI states that Cadence's universe may only hold
  US-tradable individual stocks and crypto, is managed long-only, and cannot hold
  ETFs, funds, fixed-income, cash-equivalents, or foreign listings, so that the
  evaluation's suggestions propose only in-scope actions and do not recommend
  unsupported instrument classes

#### Scenario: Prompt lists the current holdings so suggestions avoid duplicates

- **WHEN** an evaluation is generated for a universe that already holds a set of
  assets
- **THEN** the prompt lists those assets grouped by sector (ticker and name, with
  ineligible holdings flagged and crypto grouped), and instructs the AI to suggest
  only additions whose tickers are not already in that roster, so the evaluation
  does not recommend adding an asset the universe already contains
