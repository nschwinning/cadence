## ADDED Requirements

### Requirement: Recommendation run model selection

The recommend (universe) and watchlist run-create forms SHALL let a user choose
the AI model for the run from the shared model catalog, defaulting the selection
to the configured default recommender model. The recommendation run detail/list
SHALL display the model each run used.

#### Scenario: Form offers a model selector defaulted to the configured model

- **WHEN** a user opens the recommend or watchlist run-create form
- **THEN** it SHALL present a model selector populated from the model catalog with
  the configured default recommender model pre-selected

#### Scenario: Selected model is submitted with the run

- **WHEN** a user picks a model and starts the run
- **THEN** the run SHALL be created with that model

#### Scenario: Run displays the model it used

- **WHEN** a user views a recommendation run in the list or detail view
- **THEN** the UI SHALL show the model that run used
