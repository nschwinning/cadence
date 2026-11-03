## MODIFIED Requirements

### Requirement: Strategy explanation navigation entry and page

The application shell SHALL offer, within the Bots area, a navigation affordance to a
**strategy guide index**, and SHALL mark it active when shown, consistent with the
shell's other navigation entries. The index SHALL list **every** strategy in the
strategy-bots catalog, each as an entry showing the strategy's display name and a short
blurb, and each SHALL link to that strategy's **own detail page**. The index SHALL also
document, **once**, the strategy-agnostic capital management and risk controls the bots
apply — ATR risk-based position sizing, the maximum per-name cap, the maximum number of
concurrent positions, the shared capital budget ceiling, take-profit, stop-loss, and the
drawdown kill-switch — in a readable grouped "Capital & risk" section; this documentation
SHALL NOT be repeated on the individual strategy pages.

Each **per-strategy detail page** SHALL resolve its strategy from the catalog by the
strategy key in its route and SHALL display that strategy's explanation text, accompanied
by an **illustrative chart** for strategies that have one (for the MA Crossover strategy,
a chart depicting a fast and a slow moving average with entry and exit markers at their
crossovers); a strategy with no illustrative chart SHALL render its explanation without
one. When the route names a strategy that is not in the catalog, the detail page SHALL
show a not-found state rather than a blank or broken page.

While the strategy catalog is loading, both the index and a detail page SHALL show a
loading state, and if the catalog request fails they SHALL show an error state rather than
a blank or broken page.

#### Scenario: Navigate to the strategy explanation page

- **WHEN** a user selects the strategy guide affordance in the Bots area
- **THEN** the application SHALL render the strategy guide index within the shell and mark
  the entry active without a full page reload

#### Scenario: Index lists every catalog strategy with links to its page

- **WHEN** the strategy guide index loads the strategy catalog successfully
- **THEN** it SHALL show an entry for each strategy in the catalog with its display name
  and blurb, and each entry SHALL link to that strategy's own detail page

#### Scenario: Strategy mechanic explained with an illustrative chart

- **WHEN** a user opens a strategy's detail page and the catalog loads successfully
- **THEN** it SHALL display that strategy's explanation text, and for a strategy that has
  an illustrative chart (such as MA Crossover) it SHALL show that chart with fast and slow
  moving averages and entry/exit markers at their crossovers; a strategy without a chart
  SHALL render the explanation without one

#### Scenario: Unknown strategy key shows a not-found state

- **WHEN** a strategy detail page is opened for a key that is not in the catalog
- **THEN** it SHALL show a not-found state rather than a blank or broken page

#### Scenario: Risk controls and capital management documented

- **WHEN** the strategy guide index is shown
- **THEN** it SHALL document ATR risk-based sizing, the per-name cap, the maximum
  concurrent positions, the shared budget ceiling, take-profit, stop-loss, and the
  drawdown kill-switch in a readable grouped section, documented once on the index and not
  duplicated on the individual strategy pages

#### Scenario: Loading and error states

- **WHEN** the strategy catalog is loading or the request fails
- **THEN** the index and detail pages SHALL show a loading state while pending and an error
  state on failure instead of the content
