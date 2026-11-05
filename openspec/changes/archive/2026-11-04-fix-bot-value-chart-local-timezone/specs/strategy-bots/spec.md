## ADDED Requirements

### Requirement: Bot value chart local-timezone labels

The bot detail value chart SHALL label its intraday (`5min` and `hourly`) axis ticks and tooltips using the viewer's local timezone, so the chart's clock times agree with the trade timestamps and live-value times shown elsewhere on the same page (which already render in local time). For intraday resolutions the axis label SHALL be the point's local-time `dd.MM HH:mm` and the tooltip SHALL be its local-time `dd.MM.yyyy HH:mm`, derived from the point's captured instant rather than from UTC clock parts. The `daily` and `monthly` resolutions SHALL continue to label each point by its snapshot's calendar date (no clock time), unchanged by this requirement.

#### Scenario: Intraday axis and tooltip use local time

- **WHEN** the bot value chart is shown at `5min` or `hourly` resolution and a point was captured at an instant whose local-timezone clock time differs from its UTC clock time
- **THEN** the point's axis label SHALL be its local-time `dd.MM HH:mm` and its tooltip SHALL be its local-time `dd.MM.yyyy HH:mm` — matching the page's trade timestamps — and NOT the UTC clock value

#### Scenario: Daily and monthly remain calendar-date labels

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution
- **THEN** each point SHALL continue to be labelled by its snapshot's calendar date, with no clock-time component and no day shift
