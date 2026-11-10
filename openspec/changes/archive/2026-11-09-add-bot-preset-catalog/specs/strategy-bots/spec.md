## ADDED Requirements

### Requirement: Bot preset catalog

The system SHALL maintain a fixed catalog of **bot presets**. Each preset SHALL have a
stable key, a display name, a short description, a reference to the course algorithm it
reproduces, the key of the registered strategy it uses, that strategy's parameters, and
the risk controls it applies — the take-profit and stop-loss thresholds (each either a
percentage or off) and the drawdown kill-switch limit. A preset SHALL NOT fix the
session's capital, traded assets, benchmark, label, or position-sizing settings; those
remain choices made when a session is created. Every preset's strategy parameters SHALL be
valid for its strategy. Each registered strategy SHALL have exactly one **default
preset**. The system SHALL let a client list the presets, and the listing SHALL report,
for each preset, all of the fields above and whether it is its strategy's default.

The catalog SHALL include these presets, reproducing the reference-course recipes:

- **MA Crossover (Algo 6)** — default for the moving-average crossover strategy: fast
  period 5, slow period 12; take-profit 1%, stop-loss 2%, drawdown limit 5%.
- **RSI Mean Reversion (Algo 16)** — default for the RSI mean-reversion strategy:
  period 14, oversold 30, exit level 50; take-profit 0.5%, stop-loss 1%, drawdown
  limit 5%.
- **Turtle Breakout (Algo 25)** — default for the Donchian range-breakout strategy:
  Turtle version, entry period 20, exit period 10; take-profit off, stop-loss off,
  drawdown limit 5%.
- **Smart Range Breakout (Algo 8)** — Donchian range-breakout strategy, Locked version,
  channel period 20, ATR padding multiplier 0.5; take-profit 0.5%, stop-loss 2%,
  drawdown limit 5%.

#### Scenario: List presets

- **WHEN** a client requests the preset catalog
- **THEN** the system SHALL return every preset with its key, display name, description,
  course reference, strategy key, strategy parameters, take-profit, stop-loss, drawdown
  limit, and whether it is its strategy's default

#### Scenario: One default preset per strategy

- **WHEN** a client requests the preset catalog
- **THEN** every registered strategy SHALL have exactly one preset marked as its default

#### Scenario: Preset parameters are valid for their strategy

- **WHEN** the preset catalog is loaded
- **THEN** every preset's strategy parameters SHALL validate against its strategy's
  parameter schema

### Requirement: Preset-driven build form

The bot build form SHALL load its presets from the preset catalog rather than from
values fixed in the client. The form SHALL open preconfigured with the default preset of
the initially selected strategy. Selecting a different strategy SHALL apply that strategy's
default preset to the strategy parameters and risk controls; for the Donchian range-breakout
strategy, selecting a version SHALL apply the preset for that version. Every applied value
SHALL remain editable. When the user changes any value that came from the applied preset,
the form SHALL indicate that the configuration is customized. Submitting the form SHALL
send the applied preset's key together with the configured values.

#### Scenario: Form opens with the default preset

- **WHEN** a user opens the build form
- **THEN** the strategy parameters and risk controls SHALL be filled from the default
  preset of the initially selected strategy

#### Scenario: Switching strategy applies its default preset

- **WHEN** a user selects a different strategy in the build form
- **THEN** the form SHALL apply that strategy's default preset to the strategy
  parameters and risk controls

#### Scenario: Switching Donchian version applies the version's preset

- **WHEN** a user selects a Donchian version in the build form
- **THEN** the form SHALL apply the preset for that version

#### Scenario: Editing a preset value marks the configuration customized

- **WHEN** a user changes a strategy parameter or risk control that the applied preset set
- **THEN** the form SHALL indicate that the configuration is customized, and the field
  SHALL keep the user's value

### Requirement: Session provenance on the bot detail view

The bot detail view SHALL show where a session's configuration came from: the display
name of the preset it started from, marked as customized when its configuration was
changed from that preset, or an indication that it is a custom configuration when no preset
was used.

#### Scenario: Unchanged preset session

- **WHEN** a user views a session that was created from a preset without changes
- **THEN** the detail view SHALL show that preset's display name without a customized mark

#### Scenario: Customized preset session

- **WHEN** a user views a session that was created from a preset and then changed
- **THEN** the detail view SHALL show that preset's display name marked as customized

#### Scenario: Session without a preset

- **WHEN** a user views a session that was created without a preset
- **THEN** the detail view SHALL show that the session uses a custom configuration

## MODIFIED Requirements

### Requirement: Strategy bot session lifecycle

The system SHALL let a client create a strategy-bot session bound to a single
strategy, a **set of one or more equity assets drawn from the shared asset universe**,
an initial capital amount that serves as the session's **shared capital budget**, a
benchmark, and the strategy's parameters. The client SHALL be able to choose the traded
set either as specific universe assets or as the **whole eligible universe**, in which
case the system SHALL resolve the currently eligible universe equities into the
session's traded set at creation. A session SHALL only ever trade assets that are
eligible equities in the universe; the system SHALL NOT create or admit any asset that
is not already in the universe. A bot session SHALL be persisted independently of AI
paper-trading sessions, with no foreign key to paper-trading sessions. A bot session
SHALL have a lifecycle status of active, stopped, or archived. The system SHALL let a
client stop an active session and archive a stopped session. Whenever a session
transitions to stopped — by either a manual stop or the drawdown kill-switch — the system
SHALL record the **stop reason** (manual or drawdown kill-switch) and the **stop time**.
Sessions that were already stopped before this behavior existed MAY have an absent stop
reason and stop time. Creating a bot session SHALL NOT invoke any AI model.

A client MAY create a session **from a preset** by supplying a preset key. The strategy
is then the preset's strategy; if the client also supplies a strategy key, it SHALL match
the preset's strategy. The preset SHALL provide the strategy parameters and the take-profit,
stop-loss, and drawdown limit for any of those values the client does not supply; values
the client supplies SHALL override the preset's, including explicitly turning take-profit
or stop-loss off. The session SHALL record the preset key and whether its effective
strategy parameters or risk controls differ from the preset's (**customized**). A session
created without a preset SHALL record no preset key. Every session SHALL record its
**origin**; sessions created through the client API SHALL have origin manual, and sessions
that existed before origin was recorded SHALL be treated as manual. Session reads SHALL
report the preset key, the customized flag, and the origin.

#### Scenario: Create a bot session

- **WHEN** a client creates a bot session with a valid strategy key, a set of eligible
  universe assets, an initial capital budget, a benchmark, and valid strategy parameters
- **THEN** the system SHALL persist a new active bot session bound to that set of assets
  with the budget as its starting shared capital, and return it, without invoking any AI
  model

#### Scenario: Whole-universe selection resolves the eligible set

- **WHEN** a client creates a bot session selecting the whole universe
- **THEN** the system SHALL resolve the currently eligible universe equities into the
  session's traded set at creation and trade that set

#### Scenario: Reject an unknown strategy or non-universe asset

- **WHEN** a client creates a bot session with an unregistered strategy key, or with any
  asset that is not an eligible equity in the universe
- **THEN** the system SHALL reject the request rather than creating a session, and SHALL
  NOT create a new asset

#### Scenario: Stop and archive

- **WHEN** a client stops an active bot session and later archives it
- **THEN** the session SHALL transition active → stopped → archived and SHALL no
  longer be ticked once stopped

#### Scenario: Manual stop records reason and time

- **WHEN** a client manually stops an active bot session
- **THEN** the system SHALL record the stop reason as manual and the stop time as the
  moment it stopped

#### Scenario: Create from a preset without overrides

- **WHEN** a client creates a session supplying a preset key, assets, capital, and a
  benchmark, but no strategy parameters or risk controls
- **THEN** the session SHALL use the preset's strategy, strategy parameters, take-profit,
  stop-loss, and drawdown limit, and SHALL record the preset key as not customized with
  origin manual

#### Scenario: Create from a preset with overrides

- **WHEN** a client creates a session supplying a preset key and a strategy parameter or
  risk control that differs from the preset's
- **THEN** the session SHALL use the supplied value, keep the preset's values for
  everything not supplied, and record the preset key as customized

#### Scenario: Supplied values equal to the preset are not customized

- **WHEN** a client creates a session supplying a preset key together with values that
  all equal the preset's
- **THEN** the session SHALL record the preset key as not customized

#### Scenario: Reject an unknown preset or mismatched strategy

- **WHEN** a client creates a session with an unknown preset key, or with a strategy key
  that differs from the preset's strategy
- **THEN** the system SHALL reject the request rather than creating a session

#### Scenario: Create without a preset

- **WHEN** a client creates a session without a preset key
- **THEN** the session SHALL be created exactly as before, recording no preset key, not
  customized, and origin manual
