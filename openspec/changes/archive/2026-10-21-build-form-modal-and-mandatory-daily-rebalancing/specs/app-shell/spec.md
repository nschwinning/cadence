## MODIFIED Requirements

### Requirement: AI build form asset scope and default capital

The AI portfolio build form SHALL be opened from a control on the Portfolios page and presented in a modal dialog rather than rendered inline on the page, so the page is not cluttered by the form when the user is not building a portfolio; the modal SHALL be dismissible via an explicit close control, a click on the backdrop, and the Escape key. The build form SHALL NOT offer a daily-rebalancing enrollment choice — every AI portfolio is enrolled in daily rebalancing automatically — and MAY note that all AI portfolios rebalance daily. The AI portfolio build form SHALL let the user choose the portfolio's asset scope — stocks only, crypto only, or both — defaulting to both, and SHALL let the user choose the session's benchmark from the fixed benchmark catalog, defaulting to S&P 500. The form SHALL also let the user choose the session's **AI model** from the fixed model catalog, defaulting to the configured default model. The form SHALL also let the user opt the portfolio into the **technical-indicator trend strategy** via a toggle that defaults to **off**. The form SHALL also let the user opt the portfolio into **company fundamentals** via a toggle that defaults to **off**, which when enabled supplies the session's rebalance agent with per-ticker company financials. The form SHALL also let the user opt the portfolio into **including watchlist assets** via a toggle that defaults to **off**, which when enabled adds the user's watchlist-membership assets to the candidate universe the session's AI picks from. The form SHALL also let the user opt the portfolio into an **automatic hard stop-loss** via a toggle that defaults to **off**, and SHALL let the user set the **stop-loss threshold percentage** (defaulting to the configured default) that applies when the stop-loss is enabled; the threshold control MAY be hidden or disabled while the stop-loss toggle is off. The form SHALL also let the user opt the portfolio into **portfolio risk guardrails** via a toggle that defaults to **off**, and SHALL let the user set the guardrail parameters that apply when the guardrails are enabled — the **maximum percentage per asset**, the **maximum percentage per asset class**, the **minimum number of positions**, and the **maximum invested percentage** (cash buffer) — each defaulting to its configured default; the guardrail parameter controls MAY be hidden or disabled while the guardrail toggle is off. The form SHALL also let the user opt the portfolio into **learning feedback** via a toggle that defaults to **off**, which when enabled informs the session's rebalance agent of its own recent prior-run outcomes, and SHALL let the user set the **learning window** (number of recent days, defaulting to the configured default) that applies when learning feedback is enabled; the window control MAY be hidden or disabled while the learning-feedback toggle is off. The form's allocated-capital input SHALL default to the configured default amount (10,000). The chosen asset scope SHALL be sent with the build request so the resulting portfolio is restricted to the selected asset types, the chosen benchmark SHALL be sent with the build request so the session is compared against it, the chosen model SHALL be sent with the build request so the session's AI runs execute on it, the technical-indicator opt-in SHALL be sent with the build request so the resulting session applies (or omits) the trend strategy accordingly, the company-fundamentals opt-in SHALL be sent with the build request so the resulting session enables (or omits) the fundamentals block accordingly, the watchlist-inclusion opt-in SHALL be sent with the build request so the resulting session includes (or omits) watchlist assets in its candidate universe accordingly, the stop-loss opt-in and (when enabled) threshold SHALL be sent with the build request so the resulting session applies (or omits) the automatic stop-loss accordingly, and the risk-guardrail opt-in and (when enabled) its parameters SHALL be sent with the build request so the resulting session applies (or omits) the guardrails accordingly, and the learning-feedback opt-in and (when enabled) its window SHALL be sent with the build request so the resulting session enables (or omits) learning feedback accordingly.

#### Scenario: Opening the build form opens a modal

- **WHEN** a user activates the "Build an AI portfolio" control on the Portfolios page
- **THEN** the build form SHALL be presented in a modal dialog overlaying the page rather than inline

#### Scenario: Dismissing the build modal

- **WHEN** the build modal is open and the user activates its close control, clicks the backdrop, or presses the Escape key
- **THEN** the modal SHALL be dismissed and the Portfolios page SHALL be shown without the form

#### Scenario: Form offers no daily-rebalancing choice

- **WHEN** a user opens the AI portfolio build form
- **THEN** the form SHALL NOT present any daily-rebalancing enrollment control, and the build request it submits SHALL carry no daily-rebalancing option

#### Scenario: Default form values

- **WHEN** a user opens the AI portfolio build form
- **THEN** the capital input SHALL default to 10,000, the asset scope SHALL default to both (stocks and crypto), the benchmark SHALL default to S&P 500, the model SHALL default to the configured default model, the technical-indicator trend-strategy toggle SHALL default to off, the company-fundamentals toggle SHALL default to off, the include-watchlist-assets toggle SHALL default to off, the automatic stop-loss toggle SHALL default to off, the risk-guardrails toggle SHALL default to off, the learning-feedback toggle SHALL default to off, and the learning-window control SHALL default to the configured default

#### Scenario: Selecting an asset scope

- **WHEN** a user selects stocks only (or crypto only) and submits the build form
- **THEN** the UI SHALL send the selected asset scope with the build request

#### Scenario: Selecting a benchmark

- **WHEN** a user selects a benchmark from the catalog and submits the build form
- **THEN** the UI SHALL send the selected benchmark with the build request

#### Scenario: Selecting a model

- **WHEN** a user selects a model from the model catalog and submits the build form
- **THEN** the UI SHALL send the selected model with the build request so the resulting session's AI runs execute on it

#### Scenario: Opting into the technical-indicator trend strategy

- **WHEN** a user enables the technical-indicator trend-strategy toggle and submits the build form
- **THEN** the UI SHALL send the technical-indicator opt-in with the build request so the resulting session applies the trend strategy

#### Scenario: Leaving the trend strategy off

- **WHEN** a user submits the build form without enabling the technical-indicator toggle
- **THEN** the UI SHALL send the build request with the opt-in off so the resulting session does not apply the trend strategy

#### Scenario: Opting into company fundamentals

- **WHEN** a user enables the company-fundamentals toggle and submits the build form
- **THEN** the UI SHALL send the company-fundamentals opt-in with the build request so the resulting session supplies the fundamentals block to its rebalance agent

#### Scenario: Leaving company fundamentals off

- **WHEN** a user submits the build form without enabling the company-fundamentals toggle
- **THEN** the UI SHALL send the build request with the fundamentals opt-in off so the resulting session supplies no fundamentals block

#### Scenario: Opting into including watchlist assets

- **WHEN** a user enables the include-watchlist-assets toggle and submits the build form
- **THEN** the UI SHALL send the watchlist-inclusion opt-in with the build request so the resulting session includes the user's watchlist-membership assets in its candidate universe

#### Scenario: Leaving watchlist assets off

- **WHEN** a user submits the build form without enabling the include-watchlist-assets toggle
- **THEN** the UI SHALL send the build request with the watchlist-inclusion opt-in off so the resulting session's candidate universe excludes watchlist-membership assets

#### Scenario: Opting into the automatic stop-loss

- **WHEN** a user enables the automatic stop-loss toggle, sets a threshold percentage, and submits the build form
- **THEN** the UI SHALL send the stop-loss opt-in and the chosen threshold with the build request so the resulting session applies the automatic stop-loss

#### Scenario: Leaving the stop-loss off

- **WHEN** a user submits the build form without enabling the automatic stop-loss toggle
- **THEN** the UI SHALL send the build request with the stop-loss off so the resulting session does not apply an automatic stop-loss

#### Scenario: Opting into the risk guardrails

- **WHEN** a user enables the risk-guardrails toggle, sets the maximum-per-asset, maximum-per-class, minimum-positions, and maximum-invested values, and submits the build form
- **THEN** the UI SHALL send the guardrail opt-in and the chosen parameters with the build request so the resulting session applies the guardrails

#### Scenario: Leaving the guardrails off

- **WHEN** a user submits the build form without enabling the risk-guardrails toggle
- **THEN** the UI SHALL send the build request with the guardrails off so the resulting session applies no allocation caps

#### Scenario: Opting into learning feedback

- **WHEN** a user enables the learning-feedback toggle, sets a learning window, and submits the build form
- **THEN** the UI SHALL send the learning-feedback opt-in and the chosen window with the build request so the resulting session enables learning feedback with that window

#### Scenario: Leaving learning feedback off

- **WHEN** a user submits the build form without enabling the learning-feedback toggle
- **THEN** the UI SHALL send the build request with learning feedback off so the resulting session does not apply learning feedback
