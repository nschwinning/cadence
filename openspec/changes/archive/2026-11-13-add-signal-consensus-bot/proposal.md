## Why

Tier 4 of the strategy-bot roadmap (`docs/trading-bots-roadmap.md`) has two bots left; next is
**Multi-Signal Consensus** (#16, course Algo 43, "Multi-Signal Mean Reversion Consensus Engine").
Every catalog strategy today acts on one indicator; this one lets eight independent
mean-reversion readings vote and only buys when enough agree, giving manual users and the AI
orchestrator a deliberately conservative, agreement-based dip buyer.

## What Changes

- New strategy **Multi-Signal Consensus** (`signal_consensus`), pure, stateless and long-only.
  Over the latest `window` closes (default 10) eight signals each vote +1 (oversold), −1
  (overbought) or 0: **z-score** (beyond ±1), **SMA deviation** (beyond ±1%), **RSI** (below 30 /
  above 70), **Bollinger** (outside mean ± `bb_k` σ), **percentile rank** (below 10% / above
  90%), **median** (beyond ±0.2%), **gradient** (close vs the mean of the latest 5) and **range**
  (within 0.1% of the window low / high). While flat, enter long when the vote sum is at least
  `consensus` (default 3); while holding, HOLD — every exit is the engine's take-profit /
  stop-loss bracket and drawdown kill-switch, as in the course.
- Course deviations, by decision:
  - **RSI fixed**: the course keeps only 10 prices but RSI(14) needs 15, so RSI never votes; the
    bot gives RSI its own `rsi_period + 1` closes so all eight signals vote. The course's simple-
    average RSI formula is kept.
  - **Rupee amounts as percent of price**: median ±₹2 → ±0.2%, range ₹1 → 0.1%, take-profit ₹5 →
    0.5%, stop-loss ₹3 → 0.3% (the course price is ~₹1,000; as done for Algo 48).
  - The course short leg is dropped; overbought (−1) votes still lower the score.
- One catalog preset: **Multi-Signal Consensus (Algo 43)** — default: window 10, consensus 3,
  RSI 14, Bollinger k 2; take-profit 0.5%, stop-loss 0.3%, drawdown 5% (the course has no
  drawdown stop; 5% catalog convention).
- Build form inputs; strategy-guide illustration chart.
- Roadmap document: Multi-Signal Consensus shipped.
- No migration (`strategy_key` is free text), no new settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the Multi-Signal Consensus strategy and its preset to the catalog.

## Impact

- Backend: new `strategy_bots/signal_consensus.py`; `constants.py`, `registry.py`, `presets.py`.
- Frontend: `pages/bots/BuildBotCard.tsx`, new `pages/bots/consensusChart.ts` registered in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
- The orchestrator's preset catalog (and the Orchestrators page's preset list) gains the preset.
