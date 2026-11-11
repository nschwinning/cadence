## ADDED Requirements

### Requirement: Admin navigation entry and page

The application shell SHALL provide an "Admin" navigation entry, placed directly after the
"System" entry, leading to an Admin page. The entry SHALL indicate when it is the active view,
like the other navigation entries. The System page SHALL remain unchanged.

The Admin page SHALL show the broker account overview: account cash, buying power and total
value; the committed-cash check with its itemised contributors, committed total, account cash
and difference, visibly warning on a shortfall; the open orders; and the positions comparison
with each row's broker quantity, Cadence quantity, classification and orphan quantity. The page
SHALL offer a manual refresh. When the broker is unavailable the page SHALL say so instead of
showing figures.

Each flattenable orphan row SHALL offer a "Flatten" action, and the page SHALL offer a
"Flatten all orphans" action when at least one row is flattenable. Each action SHALL first open
a confirmation dialog naming the symbols and orphan quantities that will be sold and noting
that the final quantities are recomputed at execution. Nothing SHALL be sold unless the
operator confirms. After the action completes the page SHALL show the per-symbol outcome and
refresh the overview. Rows that are not flattenable SHALL show why (matched, shortfall, short,
or pending order) and offer no flatten action.

#### Scenario: Admin entry follows System

- **WHEN** a user views the sidebar navigation
- **THEN** it SHALL show an "Admin" entry directly after the "System" entry

#### Scenario: Admin page shows the account and cash check

- **WHEN** the operator opens the Admin page and the broker is reachable
- **THEN** the page SHALL show the account's cash, buying power and total value, the cash
  check with its contributors and difference, the open orders, and the positions comparison

#### Scenario: Shortfall is highlighted

- **WHEN** the cash check reports a shortfall
- **THEN** the page SHALL visibly warn that Cadence has committed more cash than the account
  holds

#### Scenario: Flatten requires confirmation

- **WHEN** the operator selects "Flatten" on an orphan row
- **THEN** the page SHALL show a confirmation dialog naming the symbol and orphan quantity, and
  SHALL submit nothing if the operator cancels

#### Scenario: Outcome is shown after flattening

- **WHEN** the operator confirms a flatten action
- **THEN** the page SHALL show each symbol's outcome (sold, skipped or failed with its reason)
  and refresh the overview

#### Scenario: Non-flattenable rows explain themselves

- **WHEN** a row is matched, a shortfall, short, or has a pending order
- **THEN** it SHALL show that status and offer no flatten action

#### Scenario: Broker unavailable on the Admin page

- **WHEN** the broker cannot be reached
- **THEN** the Admin page SHALL say the broker is unavailable and show no figures or flatten
  actions
