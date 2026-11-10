## MODIFIED Requirements

### Requirement: Dashboard AI cost per portfolio panel

The dashboard SHALL render a panel that lists AI (LLM) cost **per portfolio and per bot
orchestrator**, showing one row per active portfolio and one row per active orchestrator
with its display label and all-time cumulative AI cost, plus a grand total row.
Orchestrator rows SHALL be visibly marked as orchestrators so they can be told apart from
portfolios.

The panel SHALL be positioned **above the market-performers tiles** (the Universe section's
best/worst performers) and SHALL NOT sit under the range-scoped performance section.

The panel SHALL cover active portfolios and active orchestrators only and SHALL be
independent of both the dashboard range selector and the combined-equity chart's portfolio
selection — it does not react to toggling portfolios in that chart.

Rows SHALL be ordered by cost descending so the most expensive portfolios and
orchestrators surface first. Monetary values SHALL use the app's USD currency formatting.

The panel SHALL reuse the per-session AI cost tile's degradation convention: a row whose
cost is unavailable SHALL show an em dash ("—") rather than `$0.00`, and when the cost
source is unavailable the panel SHALL show an explanatory hint ("Cost tracking
unavailable") instead of fabricated figures. A row with no recorded spend SHALL show
`$0.00`.

When there are no portfolios and no orchestrators, the panel SHALL show an empty state
rather than an empty table.

#### Scenario: Panel lists portfolios by cost with a total

- **WHEN** the dashboard loads and the AI cost breakdown is available
- **THEN** the panel shows one row per active portfolio with its label and cumulative AI
  cost, ordered by cost descending
- **AND** a total row summing the per-portfolio and per-orchestrator costs

#### Scenario: Panel appears above the market-performers tiles

- **WHEN** the dashboard renders
- **THEN** the AI cost panel is positioned above the market-performers (Universe best/worst)
  tiles and not within the range-scoped performance section

#### Scenario: Panel is independent of range and chart selection

- **WHEN** the operator changes the dashboard range or toggles portfolios in the combined
  equity chart
- **THEN** the AI cost panel's rows and figures do not change

#### Scenario: Unavailable cost degrades to an em dash with a hint

- **WHEN** the cost source is unconfigured or unavailable
- **THEN** affected costs render as "—" and the panel shows a "Cost tracking unavailable"
  hint rather than `$0.00` or an error

#### Scenario: Zero spend is distinct from unavailable

- **WHEN** a portfolio has a readable cost of zero
- **THEN** its row shows `$0.00`, not an em dash

#### Scenario: Empty state with no portfolios

- **WHEN** there are no active paper-trading portfolios and no active orchestrators
- **THEN** the panel shows an empty state instead of an empty table

#### Scenario: Orchestrator rows are marked and ordered with portfolios

- **WHEN** the breakdown includes an active orchestrator
- **THEN** its row is marked as an orchestrator, shows its label and all-time cost, and is
  ordered by cost together with the portfolio rows
