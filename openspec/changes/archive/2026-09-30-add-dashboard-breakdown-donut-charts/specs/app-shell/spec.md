## ADDED Requirements

### Requirement: Dashboard asset-composition donut charts

The dashboard SHALL present the asset universe's composition by category and by sector each as a donut (ring) chart rather than a ranked count list. Each chart SHALL render one slice per breakdown entry, with the slice's angular size proportional to that entry's share of the breakdown's total count. Each chart SHALL display the breakdown's total count at its center and SHALL provide a legend mapping each slice's color to its human-readable label.

Hovering (or otherwise focusing) a slice SHALL reveal detail for that entry: its human-readable label, its exact count, and its percentage of the breakdown's total. The percentage SHALL be computed on the client from the counts; the chart SHALL NOT require any new data from the metrics endpoint.

When a breakdown has no entries, the dashboard SHALL show an empty-state message in place of the chart rather than an empty or broken chart.

#### Scenario: Composition shown as donut charts

- **WHEN** a user opens the dashboard and the asset universe has categorized and sectored assets
- **THEN** the UI SHALL render the by-category and by-sector breakdowns each as a donut chart whose slices are sized by each entry's share of the total, with the total count shown at the center and a legend identifying each slice

#### Scenario: Slice hover reveals exact value and percentage

- **WHEN** a user hovers or focuses a slice of a breakdown donut chart
- **THEN** the UI SHALL show that entry's human-readable label, its exact count, and its percentage of the breakdown's total

#### Scenario: Percentages sum across the breakdown

- **WHEN** a breakdown donut chart is displayed
- **THEN** each slice's percentage SHALL be that entry's count divided by the sum of all entries' counts in the breakdown, derived on the client without additional data from the metrics endpoint

#### Scenario: Empty breakdown

- **WHEN** a breakdown has no entries
- **THEN** the UI SHALL show an empty-state message instead of a donut chart
