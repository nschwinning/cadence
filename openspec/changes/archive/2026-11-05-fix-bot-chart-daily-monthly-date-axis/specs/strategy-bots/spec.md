## MODIFIED Requirements

### Requirement: Bot value chart local-timezone labels

The bot detail value chart SHALL label its intraday (`5min` and `hourly`) axis ticks and
tooltips using the viewer's local timezone, so the chart's clock times agree with the trade
timestamps and live-value times shown elsewhere on the same page (which already render in
local time). For intraday resolutions the axis label SHALL be the point's local-time
`dd.MM HH:mm` and the tooltip SHALL be its local-time `dd.MM.yyyy HH:mm`, derived from the
point's captured instant rather than from UTC clock parts.

The `daily` and `monthly` resolutions SHALL label each point by its snapshot's calendar
date (no clock time). Each distinct calendar period SHALL appear on the x-axis **exactly
once** — one tick per snapshot date for `daily`, one tick per calendar month for `monthly`
— carrying that period's own end-of-day value. The labelling SHALL NOT depend on the
viewer's timezone: a date SHALL never be duplicated across multiple ticks, and a period's
value SHALL never be rendered under an adjacent period's label, for a viewer in any
timezone.

#### Scenario: Intraday axis and tooltip use local time

- **WHEN** the bot value chart is shown at `5min` or `hourly` resolution and a point was
  captured at an instant whose local-timezone clock time differs from its UTC clock time
- **THEN** the point's axis label SHALL be its local-time `dd.MM HH:mm` and its tooltip
  SHALL be its local-time `dd.MM.yyyy HH:mm` — matching the page's trade timestamps — and
  NOT the UTC clock value

#### Scenario: Daily and monthly remain calendar-date labels

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution
- **THEN** each point SHALL continue to be labelled by its snapshot's calendar date, with
  no clock-time component and no day shift

#### Scenario: Daily and monthly show one label per period

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution with points on
  consecutive distinct periods (for example daily snapshots on two consecutive dates)
- **THEN** each period SHALL appear exactly once on the x-axis, labelled by its own calendar
  date (`dd.MM`) with no clock-time component, each carrying that period's end-of-day value —
  no date duplicated across ticks and no value shown under an adjacent period's label

#### Scenario: Coarse labels are stable across viewer timezones

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution to a viewer whose
  local timezone is east or west of UTC
- **THEN** each snapshot SHALL be labelled by the same calendar date regardless of the
  viewer's timezone, with no day shift and no duplicated or misaligned labels
