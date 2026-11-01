# price-ml Specification

## Purpose

A learned price-direction signal for the AI paper-trading stack: a single pooled
gradient-boosted classifier that predicts the direction of each asset's forward
~21-trading-day return from engineered price features derived from the asset's stored
daily closes (lagged trailing returns plus scale-free indicators — RSI, a
price-normalised MACD histogram, realised volatility, moving-average ratios, and
Bollinger %b — computed from those closes), validated with purged/embargoed walk-forward
so its stored confidence is honest. The signal is precomputed nightly and stored one row
per asset, read by the rebalance flow, and degrades to an explicit "unavailable" marker
rather than ever fabricating a signal or failing a run.

## Requirements

### Requirement: Pooled price-direction model

The system SHALL train a single pooled machine-learning classifier across all eligible
assets that predicts the **direction of the forward return over a configured horizon**
(defaulting to about 21 trading days). The model SHALL be a gradient-boosted tree
classifier trained in process (no external model service). It SHALL be trained on a
cross-asset feature matrix so that one model serves every asset, rather than a separate
model per asset. The horizon SHALL be configurable. The model SHALL be retrained on a
configured cadence (defaulting to weekly) while predictions are produced on the nightly
cadence, so the stored signal is stable between retrains.

#### Scenario: One pooled model serves all assets

- **WHEN** the price-ML training runs
- **THEN** the system SHALL train a single classifier over the combined feature rows of
  all eligible assets and use it to produce per-asset predictions, rather than training
  one model per asset

#### Scenario: Configured horizon

- **WHEN** the model is trained and used to label and predict
- **THEN** the target SHALL be the sign of the forward return over the configured
  horizon (defaulting to about 21 trading days)

#### Scenario: Retrain cadence distinct from inference cadence

- **WHEN** the nightly precompute runs on a day that is not a scheduled retrain day
- **THEN** the system SHALL reuse the most recently trained model to produce predictions
  rather than retraining from scratch

### Requirement: Feature assembly from stored data

The system SHALL assemble the model's features from data already stored by the system —
the asset's stored daily close price history — without requiring any additional
market-data fetch at training or inference time beyond the price history already
ingested. The features SHALL be the lagged trailing returns plus scale-free indicators
computed from those closes, so the same feature SHALL be computable at every historical
row (for training) and at the latest row (for inference). Feature assembly SHALL be
deterministic given the stored inputs. An asset with fewer than the minimum required bars
of stored close history SHALL be excluded from training and SHALL yield no prediction
rather than being trained or predicted on incomplete data.

#### Scenario: Features drawn from stored price history

- **WHEN** the feature matrix is assembled
- **THEN** each row SHALL be built from the asset's stored daily closes — its lagged
  price-history returns and the scale-free indicators computed from those closes — with no
  additional per-asset market-data fetch beyond the already-ingested price history

#### Scenario: Insufficient history excluded

- **WHEN** an asset has fewer than the minimum required bars of stored close history
- **THEN** the asset SHALL be excluded from training and SHALL produce no stored
  prediction

### Requirement: Purged walk-forward validation and stored confidence

The system SHALL evaluate the model with a **purged and embargoed walk-forward**
procedure — training on a rolling past window and evaluating on a later, non-overlapping
window, purging and embargoing samples whose label horizons overlap the evaluation
window — so the reported accuracy is not inflated by overlapping multi-period labels. For
each produced prediction the system SHALL store, alongside the predicted direction and
its probability, a **recent out-of-sample accuracy** derived from this walk-forward
evaluation, so a consumer can convey the signal's reliability honestly. Validation and
feature assembly SHALL be deterministic given fixed inputs and a fixed random seed.

#### Scenario: Walk-forward purges overlapping labels

- **WHEN** the model is evaluated to produce its recent out-of-sample accuracy
- **THEN** the evaluation SHALL use a rolling past-train / future-test split that purges
  and embargoes samples whose forward-return horizon overlaps the evaluation window

#### Scenario: Prediction carries its recent out-of-sample accuracy

- **WHEN** a per-asset prediction is produced
- **THEN** it SHALL be stored with its predicted direction, the prediction probability,
  and a recent out-of-sample accuracy from the walk-forward evaluation

### Requirement: Nightly precompute and per-asset signal storage

The system SHALL expose a cron-guarded endpoint, guarded by the shared cron token, that
runs the price-ML precompute and SHALL store the result as **one signal row per asset**,
capturing at least the predicted direction, the prediction probability, the recent
out-of-sample accuracy, the horizon, the as-of date, the model version, and the bar
count the features were drawn from. The precompute SHALL be sequenced in the nightly cron
ordering to run after the technical-indicators precompute, both consuming the daily price
history ingested earlier. Storage SHALL replace the prior signal for an asset (one current
signal per asset). The system SHALL expose reads returning the latest stored signal for a
single asset and for a batch of assets, in the manner the rebalance flow consumes the
technical-indicator snapshots.

#### Scenario: Reject an unauthenticated precompute

- **WHEN** the price-ML precompute endpoint is called without a valid cron token
- **THEN** the system SHALL reject the request and compute nothing

#### Scenario: One current signal per asset

- **WHEN** the precompute runs and produces a prediction for an asset
- **THEN** the system SHALL store it as that asset's single current signal row, replacing
  any prior signal for that asset

#### Scenario: Batch read of latest signals

- **WHEN** a consumer requests the latest signals for a set of assets
- **THEN** the system SHALL return the most recent stored signal for each asset that has
  one, omitting assets with no stored signal

### Requirement: Graceful degradation of the price-ML signal

The price-ML signal SHALL be strictly additive and non-blocking. When an asset has no
stored signal, when its stored signal is older than a configured staleness bound, or when
the precompute cannot run, the system SHALL yield an explicit **"ML signal unavailable"**
result for the affected assets rather than raising, so a consumer (the rebalance flow)
can mark those assets unavailable and proceed unchanged. A failure within the precompute
for one asset SHALL NOT abort the precompute for the others, and the price-ML path SHALL
never fail a rebalance.

#### Scenario: Missing or stale signal degrades

- **WHEN** a consumer requests the signal for an asset that has no stored signal or whose
  signal is older than the staleness bound
- **THEN** the system SHALL yield "ML signal unavailable" for that asset rather than
  raising

#### Scenario: Per-asset precompute failure is isolated

- **WHEN** producing a prediction for one asset fails during the precompute
- **THEN** the precompute SHALL continue for the remaining assets rather than aborting
