## Why

The last open roadmap bot (`docs/trading-bots-roadmap.md`, Tier 4 #17) is the **Bayesian Trend
Predictor** (course Algo 33). Every catalog strategy today uses fixed indicator thresholds; this one
classifies the recent returns as an up, flat or down regime with Bayes' rule and trades only a
confident up-regime — a probabilistic trend follower for manual users and the AI orchestrator.
Shipping it completes the roadmap.

## What Changes

- New strategy **Bayesian Trend Predictor** (`bayesian_trend`), pure, stateless and long-only:
  - Each bar's return Δ = (close − previous close) ÷ previous close gets a Gaussian likelihood
    under three states: **UP** (mean +`drift`, σ `trend_sigma`), **FLAT** (mean 0, σ `flat_sigma`)
    and **DOWN** (mean −`drift`, σ `trend_sigma`); course values 0.1% / 0.2% / 0.08%.
  - The posterior is updated sequentially (prior = previous posterior). The course carries it for
    the whole run; Cadence is stateless, so by decision it is **rebuilt each tick from a uniform
    prior over the latest `replay_bars` returns** (default 20).
  - While flat: enter long when UP is the most likely state with posterior ≥ `threshold` (0.6) —
    the course's LONG signal. While holding: exit when DOWN is the most likely state with posterior
    ≥ `threshold` — the course's SHORT signal becomes the long exit (by decision). A FLAT spell
    keeps the position.
  - The course rounds prices to whole rupees before computing Δ; that is dropped (on a $5 stock
    every move would round to ±20%). The update runs in log space so an extreme return cannot
    underflow every likelihood to zero (mathematically identical).
- One catalog preset: **Bayesian Trend Predictor (Algo 33)** — default: course parameters, 20-bar
  replay; no take-profit or stop-loss (the course has none, by decision), drawdown 5% (catalog
  convention).
- Build form inputs; strategy-guide illustration chart.
- Roadmap document: Bayesian Trend Predictor shipped — the roadmap is complete.
- No migration (`strategy_key` is free text), no new settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the Bayesian Trend Predictor strategy and its preset to the catalog.

## Impact

- Backend: new `strategy_bots/bayesian_trend.py`; `constants.py`, `registry.py`, `presets.py`.
- Frontend: `pages/bots/BuildBotCard.tsx`, new `pages/bots/bayesianChart.ts` registered in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
- The orchestrator's preset catalog (and the Orchestrators page's preset list) gains the preset.
