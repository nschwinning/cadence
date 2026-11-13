## Context

Course Algo 43: a 10-price deque; eight vote functions (z-score ±1, SMA deviation ±1%, RSI 30/70,
Bollinger k = 2, percentile rank 10% / 90%, median ±₹2, gradient vs the mean of the latest 5,
range within ₹1 of the low/high); long when the vote sum ≥ 3, short when ≤ −3; exit at +₹5 / −₹3
only. Its RSI needs 15 prices from a 10-price deque, so it always returns 0. `News.py` only moves
the simulated price. No drawdown stop.

User decisions: fix RSI; rupee amounts as percent of price; bracket-only exits.

## Goals / Non-Goals

**Goals:** one `signal_consensus` strategy, one preset, form inputs, guide chart.

**Non-Goals:** composing votes from other catalog strategies; configurable per-vote thresholds;
a consensus-reversal exit.

## Decisions

1. **`SignalConsensusParams`** (`extra='forbid'`): `window` 10 (≥ 5, the gradient needs 5),
   `consensus` 3 (1–8), `rsi_period` 14 (≥ 2), `bb_k` 2.0 (> 0). The per-vote thresholds (z 1,
   SMA 1%, RSI 30/70, percentile 10%/90%, median 0.2%, gradient 5 bars, range 0.1%) are module
   constants — the course's fixed values; exposing all of them would bloat the form for little
   use.
2. **Required history** = `max(window, rsi_period + 1)` = 15.
3. **Statistics** mirror numpy: population σ (`np.std`), median of the window, percentile rank =
   count strictly below ÷ window. Course quirk kept: the rank can never exceed 90% (at most
   `window − 1` closes are below the latest), so the percentile signal never votes −1.
4. **RSI** is the course's simple-average form (`np.mean` of clipped diffs; 100 when the mean
   loss is 0) over its own `rsi_period + 1` closes — not Wilder, not shared with the RSI bot.
5. **Range** checks the high first, as the course does: in a window narrower than 0.1% both
   conditions hold and the vote is −1 (no dip to buy in a flat market).
6. **Reason** lists every vote (`Z +1, SMA +1, RSI 0, …, score 4`) so the bot's decision log
   shows why it bought.
7. **Preset** `signal_consensus_algo43` (default): 10 / 3 / 14 / 2.0; TP 0.005, SL 0.003, DD 0.05.
8. **Frontend**: four number inputs; `consensusChart.ts` plots a synthetic close with the vote
   score as bars on a second axis, the consensus level dashed, and an entry mark, mirroring the
   votes in a TS helper.

## Risks / Trade-offs

- A 0.3% stop on 5-minute bars is tight; trades will be short. Course-literal by decision.
- The gradient vote is never 0 except on an exact tie, so it adds steady noise to the score.

## Migration Plan

None (additive).

## Open Questions

None.
