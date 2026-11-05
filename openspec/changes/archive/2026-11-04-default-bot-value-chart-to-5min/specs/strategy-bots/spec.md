## ADDED Requirements

### Requirement: Bot value chart default resolution

When a viewer enters the bot detail page, the "Bot value" chart SHALL open at the
`5min` intraday resolution by default, so the first view is the live intraday series
rather than the coarse end-of-day snapshot curve. On this initial load the resolution
switcher SHALL reflect `5m` as the active selection and the freshness indicator SHALL
mark the series as intraday. The viewer SHALL still be able to switch to any other
supported resolution (`hourly`, `daily`, `monthly`); the chosen default does not remove
or reorder any switcher option.

#### Scenario: Chart opens at the 5-minute resolution

- **WHEN** a viewer enters the bot detail page and the value chart first loads
- **THEN** the chart SHALL request and display the `5min` intraday resolution, the
  resolution switcher SHALL show `5m` as the active selection, and the freshness
  indicator SHALL mark the series as intraday

#### Scenario: Viewer can still switch away from the default

- **WHEN** the value chart has opened at its `5min` default and the viewer selects a
  coarser resolution such as `daily`
- **THEN** the chart SHALL load that resolution and its freshness indicator SHALL mark
  the series as end-of-day, exactly as when any resolution is selected
