## ADDED Requirements

### Requirement: Bot value chart freshness indicator

The bot detail value chart SHALL display a freshness indicator whose meaning
reflects the currently selected resolution, so the label never contradicts the
data on screen. When an intraday resolution (`5min` or `hourly`) is selected —
the resolutions that plot per-tick intraday points — the indicator SHALL mark
the series as intraday, conveying that the latest point is the most recently
captured tick and can lag the live performance figures. When a coarse resolution
(`daily` or `monthly`) is selected — the resolutions that read the end-of-day
snapshot curve — the indicator SHALL mark the series as end-of-day. Switching the
resolution SHALL update the indicator accordingly.

#### Scenario: Coarse resolution marks the chart as end-of-day

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution
- **THEN** its freshness indicator SHALL mark the series as end-of-day

#### Scenario: Intraday resolution marks the chart as intraday

- **WHEN** the user selects the `5min` or `hourly` resolution for the bot value
  chart
- **THEN** its freshness indicator SHALL mark the series as intraday rather than
  end-of-day

#### Scenario: Switching back to a coarse resolution restores the end-of-day marker

- **WHEN** the user switches from an intraday resolution back to `daily` or
  `monthly`
- **THEN** the freshness indicator SHALL mark the series as end-of-day again
