## ADDED Requirements

### Requirement: Asset-composition donut charts

The Assets page SHALL present the asset universe's composition by category and by sector each as a donut (ring) chart. Each chart SHALL render one slice per breakdown entry, with the slice's angular size proportional to that entry's share of the breakdown's total count, and SHALL display the breakdown's total count at its center. The two charts SHALL be rendered as equal-sized tiles.

Slice identity SHALL be revealed on hover or keyboard focus rather than through a persistent legend: hovering or focusing a slice SHALL reveal that entry's human-readable label, its exact count, and its percentage of the breakdown's total. The percentage SHALL be computed on the client from the counts; the charts SHALL NOT require any new data from the metrics endpoint.

When a breakdown has no entries, the page SHALL show an empty-state message in place of the chart rather than an empty or broken chart.

The Dashboard SHALL NOT render these asset-composition donut charts.

#### Scenario: Composition shown as equal-sized donut charts on the Assets page

- **WHEN** a user opens the Assets page and the asset universe has categorized and sectored assets
- **THEN** the UI SHALL render the by-category and by-sector breakdowns each as a donut chart whose slices are sized by each entry's share of the total, with the total count shown at the center, and the two charts SHALL be equal-sized tiles

#### Scenario: Slice hover reveals exact value and percentage

- **WHEN** a user hovers or focuses a slice of a breakdown donut chart
- **THEN** the UI SHALL show that entry's human-readable label, its exact count, and its percentage of the breakdown's total

#### Scenario: No persistent legend

- **WHEN** a breakdown donut chart is displayed
- **THEN** the chart SHALL NOT render a persistent list mapping each slice's color to its label; slice identity is available only on hover or keyboard focus

#### Scenario: Percentages sum across the breakdown

- **WHEN** a breakdown donut chart is displayed
- **THEN** each slice's percentage SHALL be that entry's count divided by the sum of all entries' counts in the breakdown, derived on the client without additional data from the metrics endpoint

#### Scenario: Empty breakdown

- **WHEN** a breakdown has no entries
- **THEN** the UI SHALL show an empty-state message instead of a donut chart

#### Scenario: Dashboard no longer shows the donut charts

- **WHEN** a user opens the Dashboard
- **THEN** the asset-composition donut charts SHALL NOT appear there

## REMOVED Requirements

### Requirement: Dashboard asset-composition donut charts

**Reason**: The asset-composition donut charts move from the Dashboard to the Assets page, lose their persistent legend (identity is hover/focus-only), and are rendered as equal-sized tiles. Replaced by the "Asset-composition donut charts" requirement.
