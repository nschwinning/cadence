## ADDED Requirements

### Requirement: Archive controls for sessions and portfolios

The UI SHALL let a user archive and unarchive paper-trading sessions and portfolios.
The session list, the session detail view, and the portfolio list SHALL each offer an
archive action for eligible items and an unarchive action for archived items. The
session archive action SHALL be available only for a stopped session. Archived items
SHALL be hidden from the default session and portfolio lists, and each list SHALL
provide a "Show archived" toggle that reveals archived items and visibly marks them as
archived. After archiving or unarchiving, the affected list SHALL reflect the change
without requiring a manual page reload.

#### Scenario: Archive a stopped session from the UI

- **WHEN** a user invokes the archive action on a stopped session
- **THEN** the UI SHALL archive the session and remove it from the default session
  list

#### Scenario: Show and unarchive archived items

- **WHEN** a user enables the "Show archived" toggle on the session or portfolio list
- **THEN** the UI SHALL display archived items marked as archived and SHALL offer an
  unarchive action that restores an item to the default list

#### Scenario: Archive action limited to eligible items

- **WHEN** a user views a session that is active or paused, or a portfolio that has an
  active or paused session
- **THEN** the UI SHALL NOT offer an enabled archive action for that item
