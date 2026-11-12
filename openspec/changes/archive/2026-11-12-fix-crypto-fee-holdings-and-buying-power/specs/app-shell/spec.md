## MODIFIED Requirements

### Requirement: Admin navigation entry and page

The application shell SHALL provide an "Admin" navigation entry, placed directly after the
"System" entry, leading to an Admin page. The entry SHALL indicate when it is the active view,
like the other navigation entries. The System page SHALL remain unchanged.

The Admin page SHALL show the broker account overview: account cash, cash buying power, margin
buying power and total value; the committed-cash check with its itemised contributors, committed total, account cash
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
bought unless the operator confirms. Each crypto row eligible for a fee write-off SHALL offer a
"Write off" action showing the quantity that would be removed from Cadence's records, and the page
SHALL offer "Write off all" when at least one row is eligible; each SHALL first open a
confirmation dialog stating that Cadence's records are lowered to the account's holding and no
order is sent. After the action completes the page SHALL show the
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

#### Scenario: Write off requires confirmation

- **WHEN** the operator selects "Write off" on an eligible crypto row
- **THEN** the page SHALL show a confirmation naming the coin and quantity, stating that no order
  is sent, and SHALL change nothing if the operator cancels


### Requirement: Dashboard broker account tile

The dashboard SHALL show a "Broker account" section containing a tile with the shared broker
account's **free capital** — the capital still usable for new bots and AI portfolios —
defined as the lower of (a) the account's cash excluding short-sale proceeds minus the cash
Cadence has committed (the committed-cash check's difference) and (b) the account's buying
power, taken as the lower of its cash buying power and its margin buying power as reported by the
broker — Cadence never borrows, and the broker rejects any buy beyond its buying power regardless
of cash. The tile SHALL also show the committed total, the account cash and the
buying power it is measured against, in the app's USD formatting, and SHALL link to the Admin
page. The tile SHALL be account-wide: it SHALL NOT react to the dashboard
range selector or to the combined-equity chart's portfolio selection. It SHALL refresh
periodically like the rest of the live dashboard figures.

The tile SHALL warn:

- with an amber "low capital" warning when free capital is positive but below $1,000, the
  smallest capital a new bot or AI portfolio can be built with;
- with a red "no buying power" warning when that buying power (the lower of cash and margin
  buying power) is zero or negative,
  stating that the broker rejects every buy until margin is freed (for example by covering
  short positions);
- with a red "no capital left" warning when free capital is zero or negative while buying power
  remains, stating that new bots or portfolios cannot be funded;
- with a red "short positions" warning when the account holds one or more short positions,
  stating how many and their total value.

The short-positions warning SHALL be shown together with whichever capital warning applies. When none applies the tile SHALL
show no warning. When the broker account cannot be read the tile SHALL say the broker is
unavailable instead of showing figures or warnings.

#### Scenario: Healthy account

- **WHEN** free capital is $25,000 and the account holds no short positions
- **THEN** the tile SHALL show $25,000 of free capital, the committed total, account cash and
  buying power, and no warning

#### Scenario: Low capital

- **WHEN** free capital is $600
- **THEN** the tile SHALL show an amber low-capital warning

#### Scenario: No capital left

- **WHEN** free capital is zero or negative while the account still has buying power
- **THEN** the tile SHALL show a red warning that no capital is left for new bots or
  portfolios

#### Scenario: Buying power caps free capital

- **WHEN** Cadence's cash arithmetic leaves $25,000 free but the account's buying power is
  $8,000
- **THEN** the tile SHALL show $8,000 of free capital

#### Scenario: No buying power

- **WHEN** the account's buying power is $0 while short positions tie up its margin
- **THEN** the tile SHALL show $0 of free capital and a red "no buying power" warning together
  with the short-positions warning, and no "no capital left" warning

#### Scenario: Short positions

- **WHEN** the account holds two short positions worth $201,000 in total
- **THEN** the tile SHALL show a red warning naming two short positions and $201,000

#### Scenario: Broker unavailable

- **WHEN** the broker account cannot be read
- **THEN** the tile SHALL say the broker is unavailable and show no figures or warnings

#### Scenario: Independent of range and selection

- **WHEN** the operator changes the dashboard range or deselects portfolios in the equity chart
- **THEN** the tile's figures SHALL NOT change

#### Scenario: Margin buying power does not inflate free capital

- **WHEN** Cadence's arithmetic leaves $40,000 free, cash buying power is $30,000 and margin
  buying power is $325,000
- **THEN** the tile SHALL show $30,000 of free capital

