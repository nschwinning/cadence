## Context

The AI paper-trading rebalance agent reasons over price, technical indicators,
fundamentals, learning feedback, and its own prompt. It has never seen a **learned
forward-return signal**. The most deployable branch of ML-for-trading research is
consistent: on tabular, noisy, data-limited market data, **gradient-boosted trees** match
or beat deep sequence models on directional accuracy while training in milliseconds on CPU
and staying interpretable — a good fit for a Raspberry Pi deployment. The sibling
`trading-bot` repo already ships a `RandomForestClassifier` price strategy (features
`return_1d, return_5d, volatility, sma50, sma200`; target next-day up/down; `.joblib`
artifact cache), and Cadence already computes and stores ~18 technical indicators per asset
nightly — ready-made features.

We want to feed a learned signal into the *existing* stack as a per-session opt-in, without
disturbing the long-only output contract, the executor, valuation, or guardrails. The
established precedent is the **company-fundamentals** opt-in: a build-time-frozen flag, a
new rebalance prompt version, and a per-ticker block attached to candidates and holdings
with a defensive prompt and an explicit "unavailable" marker. This change mirrors that
precedent and adds a new precompute capability modelled directly on `technical_indicators`
(nightly cron job, one stored row per asset, flow reads the stored rows). Unlike the
news-sentiment proposal, the model is **light enough to run in process** — no sidecar.

## Goals / Non-Goals

**Goals (v1)**
- A new `price_ml` capability: assemble a cross-asset feature matrix from the stored
  technical indicators + lagged price-history returns; train **one pooled
  `HistGradientBoostingClassifier`** (scikit-learn) to predict the sign of each asset's
  forward ~21-trading-day return; evaluate with purged/embargoed walk-forward; store one
  signal row per asset (direction, probability, recent OOS accuracy, horizon, as-of date,
  model version, bar count). Retrain weekly, infer nightly.
- A cron-guarded precompute endpoint sequenced after the technical-indicators run; batch
  reads mirroring `get_latest_snapshot(s)`.
- Opt-in per-session `use_price_ml` flag, default off, frozen at build, honored on
  rebalance (including the routed initial allocation) when the frozen prompt version ≥ the
  price-ML-aware version.
- A per-ticker advisory price-ML block on candidates and holdings; explicit "ML signal
  unavailable" marker; defensive prompt; long-only contract preserved.
- Graceful degradation: no signal / stale signal / precompute down → "unavailable", never a
  failed rebalance.
- Surfaced: build-form toggle (default off) + session-detail fact tile.

**Non-Goals (v1)**
- Shorting / long-short. A down signal only avoids/trims. Long-short is a separate track
  touching executor/valuation/guardrails.
- A deterministic weight tilt — the signal is advisory prompt input only.
- Changing the AI output schema, the executor, valuation, guardrails, or rebalance
  scheduling.
- Per-asset models, deep sequence models (LSTM/CNN/Transformer), an external model service,
  or GPU inference.
- Excess-over-benchmark labels, regression targets, multi-horizon ensembles, or online
  learning — v1 is a single pooled binary direction classifier at one horizon.
- Backfilling historical signals; attaching the block on the (dead) build prompt path.

## Decisions

### In-process pooled gradient-boosted classifier (no sidecar)
`sklearn.ensemble.HistGradientBoostingClassifier` trains in milliseconds–seconds on CPU for
our universe (~100–150 assets × a few thousand daily bars), needs no GPU, and ships aarch64
wheels — so it runs in the backend process on the Pi, unlike the transformer in the
news-sentiment proposal which required a container. **One pooled model** trains on the
combined feature rows of all eligible assets: far more training rows than any single ticker
provides, better generalization, and one artifact to cache. Per-asset models were rejected
as data-thin.

**Why gradient boosting over deep nets:** the research consensus on noisy, data-limited
tabular market data favors gradient-boosted trees for directional accuracy, interpretability
(feature importances), and CPU-cheap training — all decisive for a Pi deployment.

### Target: sign of the forward ~21-trading-day return
The label is the sign of the forward ~1-month return (raw forward-return sign, **not**
excess-over-benchmark). ~21 trading days balances signal-to-noise (longer horizons carry
more signal than daily noise), actionability against the daily/weekly/monthly rebalance
cadences, and churn/cost (a monthly-ish horizon implies fewer, more durable tilts).
Transaction cost is framed in the prompt, not baked into the label. The horizon is a
configurable setting.

### Features reuse stored indicators + lagged returns
Feature rows are assembled from the already-stored per-asset `technical_indicator` columns
(the ~18 indicators the nightly TI run computes) plus lagged returns derived from
`price_history`. No extra per-asset market-data fetch beyond what the TI precompute already
does. Feature assembly is deterministic given the stored inputs. An asset below a minimum
bar count or missing required stored features is excluded from training and yields no
prediction.

### Purged/embargoed walk-forward + stored OOS accuracy
Overfitting is the central hazard of ML-for-trading, compounded here because a ~21-day label
overlaps 21 consecutive samples. Evaluation uses a **purged and embargoed walk-forward**:
roll a past-train / future-test window forward, and purge+embargo samples whose label
horizon overlaps the test window so the reported accuracy is not overlap-inflated. Each
stored prediction carries a **recent out-of-sample accuracy** from this evaluation, which
the prompt surfaces so the agent can discount a weak model. Fixed random seed for
determinism.

### Precompute + storage mirror `technical_indicators`
A new `price_ml` package (`models.py`, `service.py`, `errors.py`, `constants.py`, plus
feature-assembly and training/eval modules and a background job) mirrors the
`technical_indicators` package. A cron-guarded endpoint (shared `X-Cron-Token` via
`require_valid_cron_token`) runs the precompute, **sequenced after** the TI cron since it
consumes the stored indicators. It stores **one `price_ml_signal` row per asset** (asset_id,
as_of_date, horizon_days, direction, probability, recent_oos_accuracy, model_version,
feature_as_of, bar_count), replacing the prior row. Reads expose `get_latest_ml_signal` /
`get_latest_ml_signals` exactly as the TI seam does. **Retrain weekly, infer nightly:** the
trained model is cached (joblib-style, as in trading-bot's `model_store`) and reused on
non-retrain nights so the stored signal is stable between retrains; retrain-every-run is a
possible later simplification.

### Rebalance attachment mirrors fundamentals (REBALANCE-ONLY)
A new `PRICE_ML_PROMPT_VERSION = 5` (next after `FUNDAMENTALS_PROMPT_VERSION = 4`); a seed
migration adds the price-ML-aware rebalance prompt (prior version's text verbatim + a
defensive per-ticker price-ML block section). The attach happens only in `flows/rebalance.py`
— on both `_candidates_from_universe` (candidates) and `_build_holdings` (holdings) — gated
by `use_price_ml AND rebalance_prompt_version >= PRICE_ML_PROMPT_VERSION`. The build flow
(`flows/build.py`) just persists the flag. Because the opening allocation is routed through
an inline initial rebalance, it inherits the price-ML block automatically — no separate
wiring. Annotation builders mirror `_fundamentals_annotation` / `_indicator_annotation`; the
block renders direction, probability, recent OOS accuracy, and as-of date, or an "ML signal
unavailable" marker.

### Flag threading mirrors `use_fundamentals`
New non-nullable `paper_trading_sessions.use_price_ml` (column migration, default off,
`server_default "false"`). Threaded through `AIBuildParams` (field + `to_payload` /
`from_payload`) → `create_session` → session row → `PaperTradingSessionRead` (explicit
router mapping), and surfaced on the build card (toggle, default off) + a session-detail
"Price ML" fact tile. No change to the AI output schema.

### Degradation contract
No stored signal, a signal older than a configured staleness bound, or a precompute that
cannot run all yield an explicit per-ticker "ML signal unavailable" rendered as a marker.
The price-ML path is wrapped so it can never raise out of the rebalance flow (same fail-open
posture as fundamentals and the unexecutable-weight redeploy). A per-asset failure inside the
precompute is isolated and does not abort the batch.

## Risks / Trade-offs

- **Modest edge, honestly measured:** we predict raw direction at one horizon; expect a
  small long-only edge, not a backtest headline. The stored recent OOS accuracy and the
  "unavailable" marker keep the signal honest and prevent the agent from over-trusting it.
- **Overfitting:** mitigated by the pooled model (more rows), purged/embargoed walk-forward,
  a fixed seed, and gradient boosting's regularization — but never eliminated. The signal is
  advisory only, so a bad model degrades the prompt, not the executor.
- **Advisory, not enforced:** the agent may ignore the signal. Accepted — keeps the output
  contract and avoids a brittle deterministic tilt.
- **New dependency (`scikit-learn`):** light, pure-CPU, aarch64 wheels, pandas+numpy already
  present. No torch/ONNX/sidecar.
- **Pi compute budget:** gradient boosting trains in milliseconds–seconds; the weekly
  retrain + nightly inference batch runs within existing cron resource limits and after the
  TI run.
- **Thin-history / crypto coverage:** assets below the minimum bar count surface as
  "unavailable" rather than noise — correct, not a bug.

## Migration Plan

Two additive Alembic migrations plus one new table migration:
1. A **signal-table** migration creating `price_ml_signal` (one row per asset, unique on
   asset_id, FK to asset with cascade, nullable prediction columns + as-of/model-version/
   bar-count metadata).
2. A **seed** migration inserting the price-ML-aware rebalance prompt version (template
   identical to the prior version plus the defensive price-ML block section).
3. A **column** migration adding `paper_trading_sessions.use_price_ml` (non-nullable,
   default off, `server_default "false"`).

Down_revision chains onto the current head; migrations round-trip. No backfill — existing
sessions read as price-ML-disabled and behave unchanged; the signal table is empty until the
first precompute runs. Rollback drops the column, the seeded prompt row, and the signal
table.

## Open Questions

- Exact feature set beyond the stored indicators + lagged returns (which lag windows; whether
  to add cross-sectional rank features) — finalize during apply with a deterministic default.
- Walk-forward window sizes (train span, test span, embargo length) and the minimum bar count
  / staleness bound — finalize during apply with conservative defaults.
- Model-artifact cache location and invalidation (metadata-compatibility gate as in
  trading-bot's `model_store`) — proposed on-disk joblib keyed by model version + feature
  schema; revisit if the Pi filesystem is a concern.
- Whether a single pooled model should carry an asset-class or one-hot ticker feature so it
  can specialize slightly — proposed to start fully pooled with no identity feature; add only
  if accuracy warrants.
