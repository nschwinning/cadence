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
transitions to stopped — by a manual stop, the drawdown kill-switch, or a bot
orchestrator — the system SHALL record the **stop reason** (manual, drawdown
kill-switch, or orchestrator) and the **stop time**. Sessions that were already stopped
before this behavior existed MAY have an absent stop reason and stop time. Creating a
bot session through the client API SHALL NOT invoke any AI model.

**Stopping sells.** A stopped session SHALL end up flat. When a session is stopped by any
path, every position it still holds SHALL be sold at market by the intraday tick while
the market is open — on the first tick after the stop, or on the next market-open tick if
the market is closed. This SHALL apply to stopped and archived sessions that still hold
positions, including sessions stopped before this behaviour existed. Once stopped, a
session SHALL NOT open new positions.

A client MAY create a session **from a preset** by supplying a preset key. The strategy
is then the preset's strategy; if the client also supplies a strategy key, it SHALL match
the preset's strategy. The preset SHALL provide the strategy parameters and the take-profit,
stop-loss, and drawdown limit for any of those values the client does not supply; values
the client supplies SHALL override the preset's, including explicitly turning take-profit
or stop-loss off. The session SHALL record the preset key and whether its effective
strategy parameters or risk controls differ from the preset's (**customized**). A session
created without a preset SHALL record no preset key. Every session SHALL record its
**origin**: sessions created through the client API SHALL have origin manual, sessions
deployed by a bot orchestrator SHALL have origin orchestrator together with a reference to
that orchestrator, and sessions that existed before origin was recorded SHALL be treated
as manual. Session reads SHALL report the preset key, the customized flag, the origin, and
the deploying orchestrator (absent for manual sessions).

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
  longer be ticked for new entries once stopped

#### Scenario: Manual stop records reason and time

- **WHEN** a client manually stops an active bot session
- **THEN** the system SHALL record the stop reason as manual and the stop time as the
  moment it stopped

#### Scenario: Stopping sells open positions at the next market-open tick

- **WHEN** a session holding open positions is stopped and an intraday tick then runs
  while the market is open
- **THEN** the tick SHALL sell every position the session holds at market, record the
  sells in the session's trade ledger, and leave the session flat and stopped

#### Scenario: Stop while the market is closed sells at the next open

- **WHEN** a session holding open positions is stopped while the market is closed
- **THEN** the session SHALL be stopped immediately and its positions SHALL be sold by the
  first tick after the market opens

#### Scenario: Previously stopped sessions with positions are flattened

- **WHEN** an intraday tick runs while the market is open and a stopped or archived session
  still holds positions from before stopping sold
- **THEN** the tick SHALL sell those positions

#### Scenario: Stopped session opens no new positions

- **WHEN** an intraday tick runs for a stopped session
- **THEN** the system SHALL NOT evaluate entries or open any position for it

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

#### Scenario: Orchestrator-deployed session records its origin

- **WHEN** a bot orchestrator deploys a session
- **THEN** the session SHALL record origin orchestrator and the deploying orchestrator, and
  session reads SHALL report both

### Requirement: Optional take-profit, stop-loss, and drawdown kill-switch

A bot session MAY configure an optional take-profit and an optional stop-loss as
percentage thresholds against each open position's entry price; when unset, neither
triggers. On each tick, for **every open position** the system SHALL exit that position
if its current price has risen to or above the take-profit threshold or fallen to or
below the stop-loss threshold, independently of the strategy signal. The system SHALL
also enforce a **whole-session** drawdown kill-switch: when a session's total value
falls by at least the configured drawdown limit from its peak, the system SHALL exit
**all** open positions and stop the session so it is no longer ticked. When the
kill-switch stops a session it SHALL record the **stop reason** as drawdown kill-switch
and the **stop time**. A session deployed by a bot orchestrator SHALL keep its own
take-profit, stop-loss and kill-switch, independently of the orchestrator's decisions.

#### Scenario: Take-profit exits

- **WHEN** an open position with a configured take-profit ticks at a price at or above
  the take-profit threshold
- **THEN** the system SHALL exit that position regardless of the strategy signal

#### Scenario: Stop-loss exits

- **WHEN** an open position with a configured stop-loss ticks at a price at or below the
  stop-loss threshold
- **THEN** the system SHALL exit that position regardless of the strategy signal

#### Scenario: Thresholds unset never trigger

- **WHEN** a session has no take-profit and no stop-loss configured
- **THEN** neither a take-profit nor a stop-loss exit SHALL occur for any position

#### Scenario: Drawdown kill-switch stops the session

- **WHEN** a session's total value has fallen by at least the drawdown limit from its
  peak
- **THEN** the system SHALL exit all open positions and stop the session, and SHALL
  record the stop reason as drawdown kill-switch and the stop time

#### Scenario: Orchestrator-deployed session keeps its own kill-switch

- **WHEN** a session deployed by a bot orchestrator reaches its drawdown limit
- **THEN** the system SHALL exit all its positions and stop it with stop reason drawdown
  kill-switch, without waiting for an orchestrator decision

### Requirement: Session provenance on the bot detail view

The bot detail view SHALL show where a session's configuration came from: the display
name of the preset it started from, marked as customized when its configuration was
changed from that preset, or an indication that it is a custom configuration when no preset
was used. When the session was deployed by a bot orchestrator, the detail view SHALL also
show that orchestrator's name as a link to the orchestrator's detail view.

#### Scenario: Unchanged preset session

- **WHEN** a user views a session that was created from a preset without changes
- **THEN** the detail view SHALL show that preset's display name without a customized mark

#### Scenario: Customized preset session

- **WHEN** a user views a session that was created from a preset and then changed
- **THEN** the detail view SHALL show that preset's display name marked as customized

#### Scenario: Session without a preset

- **WHEN** a user views a session that was created without a preset
- **THEN** the detail view SHALL show that the session uses a custom configuration

#### Scenario: Orchestrator-deployed session links its orchestrator

- **WHEN** a user views a session deployed by a bot orchestrator
- **THEN** the detail view SHALL show the orchestrator's name linking to its detail view
