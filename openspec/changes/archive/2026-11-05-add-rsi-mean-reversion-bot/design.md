## Context

The strategy-bot subsystem (see `backend/src/cadence/strategy_bots/`) uses a
three-layer model: pure `Strategy.evaluate(bars, position, params) -> Signal`
generators (layer 1), a registry mapping each `StrategyKey` to its implementation
+ params schema + required history (layer 3), and an engine that owns sizing,
TP/SL, the drawdown kill-switch, and the shared capital pool. MA Crossover is the
only strategy today. `bot_sessions.strategy_key` is a free-text `Text` column, so
new strategy keys are additive with no migration. The build-a-bot form already
renders the backend strategy catalog in its `<select>`, but its *parameter inputs*
and submit payload are hardcoded to MA Crossover's fast/slow SMA fields. See
proposal.md — Why.

## Goals / Non-Goals

**Goals:**
- Register a second strategy (RSI Mean Reversion) with the same purity and
  long-only contract as MA Crossover, reusing the existing registry/engine seams.
- Make the build-a-bot form render the *selected* strategy's parameter inputs and
  submit the matching `strategy_params`, so more than one strategy is usable.

**Non-Goals:**
- No schema-driven/auto-generated form from the backend `params_schema` (a
  bounded, explicit per-strategy input block is used instead).
- No engine, sizing, guardrail, API-shape, bar-timeframe, or short-selling change.

## Decisions

- **RSI computation — Wilder smoothing, close-only.** Match the course source:
  seed average gain/loss over the first `period` deltas, then Wilder-smooth
  forward; evaluate the RSI of the latest bar. Pure function of the bar closes.
  Alternative (simple-average RSI) rejected to stay faithful to Algo 16.
- **Signal mapping.** ENTER_LONG when flat and latest RSI `< oversold`; EXIT when
  holding and latest RSI `> exit_level`; else HOLD. The course's short entry
  (RSI > overbought) is dropped — Cadence is long-only. TP/SL/drawdown are left to
  the engine, not duplicated in the strategy. Follows the MA Crossover precedent
  (`ma_crossover.py`) of returning HOLD on insufficient history and type-checking
  the params instance.
- **Parameters.** New `RsiMeanReversionParams(StrategyParams)` with `period`
  (`int`, default 14, `ge=1`), `oversold` (`float`, default 30, `0–100`),
  `exit_level` (`float`, default 50, `0–100`), an `after` validator enforcing
  `oversold < exit_level`, and `required_history = period + 1`. `extra='forbid'`
  (inherited) rejects typos. Thresholds kept as free parameters (not hardcoded 30/50)
  so users can tune the band per bot.
- **Registration.** Add `StrategyKey.RSI_MEAN_REVERSION = "rsi_mean_reversion"` and
  its `STRATEGY_DISPLAY_NAMES` / `STRATEGY_EXPLANATIONS` entries, then one
  `StrategyRegistration` in `_REGISTRY`. No other backend change — catalog reads,
  session creation, and the tick runner all resolve through the registry already.
- **Frontend strategy-aware params.** In `BuildBotCard.tsx`, branch the "Strategy
  parameters" block and the `strategy_params` payload on `strategyKey`: MA Crossover
  keeps fast/slow; RSI shows period/oversold/exit_level. Validation (`canSubmit`)
  branches per strategy. The strategy `<select>` is unchanged (already catalog-driven).
  Add an `rsi_mean_reversion` descriptor to the `strategyCharts.ts` registry so the
  guide detail page renders an illustrative chart; a missing descriptor already
  degrades gracefully to explanation-only.

## Risks / Trade-offs

- **Form coupling.** Hardcoded per-strategy param blocks mean each future strategy
  touches `BuildBotCard.tsx`. Accepted for now (only two strategies); a
  schema-driven form is a later refactor, explicitly a non-goal here.
- **RSI edge cases.** A zero average loss over the window yields RSI = 100 (no
  divide-by-zero); with `period + 1` the warm-up is minimal, so early RSI values are
  noisier than with a longer seed — acceptable and matches the course behaviour.
- **Whole-number thresholds.** `oversold`/`exit_level` are floats on a 0–100 scale;
  the form will surface them as numeric inputs with sensible bounds to avoid
  nonsensical bands (enforced server-side by the validator regardless).
