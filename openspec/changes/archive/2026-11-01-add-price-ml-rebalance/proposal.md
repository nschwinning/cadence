## Why

Cadence's AI rebalance agent reasons over price, technical indicators, fundamentals,
and (in-flight proposals) news sentiment — but it never sees a **learned forward-return
signal**. The strongest, most deployable branch of ML-for-trading research is clear and
consistent: on tabular, noisy, data-limited market data, **gradient-boosted trees
match or beat deep sequence models** on directional accuracy (one walk-forward
benchmark: XGBoost 65% vs LSTM/CNN 52–60%) while training in milliseconds, running on a
CPU/Raspberry Pi, and remaining interpretable. The project already has a working
blueprint — the sibling `trading-bot` repo ships a `RandomForestClassifier` price
strategy with artifact caching — and Cadence already computes and stores ~18 technical
indicators per asset nightly, which are ready-made model features.

Adding an opt-in **price-ML** signal lets a session's agent weigh a learned,
honestly-validated direction estimate (with its recent out-of-sample hit-rate) alongside
its other inputs — advisory, long-only, never a deterministic tilt. It fits the existing
opt-in pattern (`use_fundamentals`, `use_technical_indicators`) and the
technical-indicators precompute architecture exactly, so it adds capability without new
runtime risk.

We scope v1 to a **single pooled gradient-boosted classifier** predicting the
**direction of the forward ~21-trading-day (~1-month) return** — the horizon with the
best signal-to-noise and lowest churn for a long-only, cost-aware portfolio — validated
with **purged/embargoed walk-forward** so the stored confidence is honest and not
overlap-inflated.

## What Changes

- A new **price-ml** capability: an in-process nightly precompute that assembles a
  cross-asset feature matrix (the stored technical indicators + lagged price-history
  returns), trains **one pooled `HistGradientBoostingClassifier`** (scikit-learn) to
  predict the sign of each asset's forward ~21-trading-day return, evaluates it with
  purged/embargoed walk-forward to produce a recent out-of-sample accuracy, and **stores
  one signal row per asset** (direction, probability, recent OOS accuracy, horizon,
  as-of date, model version, bar count). The model is **retrained weekly and inferred
  nightly** for signal stability; the job is cron-guarded and sequenced after the
  technical-indicators run. Reads mirror the technical-indicators seam
  (`get_latest_ml_signal(s)`). Thin history / stale model ⇒ explicit
  "ML signal unavailable" — never a fabricated signal, never a failed run.

- **ai-paper-trading** (modified): a new per-session **`use_price_ml`** flag, default
  **off**, frozen at build, delivered as a new rebalance prompt version (bump
  `PRICE_ML_PROMPT_VERSION`). When a session opted in **and** is frozen on a prompt
  version at or after the price-ML-aware version, its rebalances attach a per-ticker
  **price-ML advisory block** to **both** candidates and current holdings; opted-out or
  older-version sessions behave exactly as before. Mirrors the company-fundamentals
  opt-in, including the routed initial allocation. The session read model carries the
  new flag.

- **app-shell** (modified): a "Use price ML" toggle on the AI build form (defaults off)
  and a "Price ML" fact tile on the session-detail page, mirroring the
  company-fundamentals toggle/tile.

## Capabilities

### New Capabilities
- `price-ml`: a learned price-direction signal — the pooled gradient-boosted model, the
  feature assembly (reusing stored technical indicators + lagged returns), the
  purged/embargoed walk-forward validation and stored out-of-sample accuracy, the
  weekly-retrain / nightly-infer precompute, per-asset signal storage and reads, and the
  "unavailable" degradation contract.

### Modified Capabilities
- `ai-paper-trading`: the rebalance prompt gains an opt-in per-ticker price-ML advisory
  block (new `use_price_ml` flag, new price-ML-aware prompt version), and the session
  read model carries the flag.
- `app-shell`: the AI build form gains a price-ML toggle (default off) and the
  session-detail view gains a price-ML fact tile.

## Impact

- **Backend:** new `price_ml` package (`models`/`service`/`errors`/`constants`, plus
  feature-assembly and training/eval modules, and a background job) mirroring
  `technical_indicators`; new settings (horizon, retrain cadence, min-history, model
  version); a signal-table migration (`price_ml_signal`, one row per asset); a new
  seeded price-ML-aware rebalance prompt version; one column migration adding
  `paper_trading_sessions.use_price_ml`; threading through the rebalance flow,
  `AIBuildParams`, and `PaperTradingSessionRead`.
- **New dependency:** `scikit-learn` (light, aarch64 wheels; pandas + numpy already
  present). No torch, no ONNX, no sidecar — training/inference run in-process.
- **Deployment:** a new cron entry for the nightly price-ML job (docker-compose/env),
  sequenced after the technical-indicators cron; runs on the Pi within existing limits.
- **Frontend:** new build-card toggle + session-detail fact tile + the
  `AIPortfolioBuildRequest`/`PaperTradingSessionRead` type additions.
- **No change** to the AI output schema (long-only, weights ~1.0), the executor,
  valuation, guardrails, or rebalance scheduling.

## Assumptions (for review)

1. **Long-only, advisory in v1.** The signal is prompt input the agent weighs — not a
   deterministic weight tilt and never a basis for shorting. A down signal argues to
   avoid/trim.
2. **Single pooled model, not per-asset.** One cross-sectional model trains on far more
   rows and generalizes better than data-thin per-ticker models; one artifact to cache.
3. **~21-trading-day direction, raw forward-return sign** (not excess-over-benchmark) —
   best SNR/cost trade-off for a long-only portfolio; transaction cost is framed in the
   prompt, not baked into the label.
4. **Reuse stored technical indicators as features** (plus lagged `price_history`
   returns) rather than recomputing — the nightly TI run already produces them.
5. **Weekly retrain / nightly inference** for signal stability; retrain-every-run is a
   possible simplification if weekly proves too stale.
6. **Honesty over headline accuracy:** purged/embargoed walk-forward and a stored recent
   out-of-sample hit-rate; the block is marked "unavailable" below a minimum bar count
   or when the model/features are stale. Expect a modest long-only edge, not a backtest
   headline.
7. **Pi-friendly:** gradient boosting trains in milliseconds–seconds on CPU; nightly
   batch job within existing resource limits, no sidecar.

## Sequencing with the other in-flight AI-signal changes

This change shares a seam with `add-news-sentiment-rebalance`: both add a per-session
opt-in flag, a **new rebalance prompt version**, and the same per-ticker attach points in
`flows/rebalance.py` (`_candidates_from_universe` and `_build_holdings`), plus the same
`AIBuildParams` / `PaperTradingSessionRead` / `BuildAIPortfolioCard` surfaces. They are
**not functionally dependent**, but they MUST be built **sequentially, not in parallel**,
to avoid colliding on the prompt-version number and conflicting mechanically in those
shared files.

Rebalance prompt versions are **linear and cumulative** (each version = the prior
version's text verbatim + one new block; each signal's attachment is independently gated
by `rebalance_prompt_version >= <its version>` AND its opt-in flag). `PRICE_ML_PROMPT_VERSION
= 5` is pinned on the assumption that **this change ships before `add-news-sentiment-rebalance`**
(the recommended order: 5 = current head 4 + 1). If news sentiment ships first instead,
this value SHALL be rebased to **6** and the seed prompt SHALL be the then-current head
prompt (which would already contain the sentiment section) verbatim + the price-ML section.
A session frozen at an earlier version never gains a later signal — the expected
build-time-frozen behavior.
