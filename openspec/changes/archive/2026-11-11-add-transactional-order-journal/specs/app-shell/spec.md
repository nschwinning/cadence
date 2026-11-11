## MODIFIED Requirements

### Requirement: Admin navigation entry and page

The application shell SHALL provide an "Admin" navigation entry, placed directly after the
"System" entry, leading to an Admin page. The entry SHALL indicate when it is the active view,
like the other navigation entries. The System page SHALL remain unchanged.

The Admin page SHALL show the broker account overview: account cash, buying power and total
value; the committed-cash check with its itemised contributors, committed total, account cash
(excluding short-sale proceeds, with the excluded amount shown) and difference, visibly warning
on a shortfall; the open orders; the unresolved orders with a "Reconcile now" action that shows
the reconciliation result; and the positions comparison with each row's broker quantity, Cadence
quantity, classification and orphan quantity. The page SHALL offer a manual refresh. When the
broker is unavailable the page SHALL say so instead of showing figures.

Each flattenable orphan row SHALL offer a "Flatten" action, and the page SHALL offer a
"Flatten all orphans" action when at least one row is flattenable. Each shortfall or short row
without a pending order SHALL offer a "Restore" action showing the quantity that would be bought,
and the page SHALL offer a "Restore all" action when at least one row is restorable. Each action
SHALL first open a confirmation dialog naming the symbols and quantities that will be sold or
bought and noting that the final quantities are recomputed at execution. Nothing SHALL be sold or
bought unless the operator confirms. After the action completes the page SHALL show the
per-symbol outcome and refresh the overview. Rows that are neither flattenable nor restorable
SHALL show why (matched or pending order) and offer no action.

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

#### Scenario: Restore requires confirmation

- **WHEN** the operator selects "Restore" on a short or shortfall row
- **THEN** the page SHALL show a confirmation dialog naming the symbol and the quantity to buy,
  and SHALL submit nothing if the operator cancels

#### Scenario: Unresolved orders and reconcile now

- **WHEN** the overview lists unresolved orders and the operator selects "Reconcile now"
- **THEN** the page SHALL run reconciliation, show the booked, closed-out and remaining counts,
  and refresh the overview
