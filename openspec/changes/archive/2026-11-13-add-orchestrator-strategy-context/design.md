## Context

`briefing.preset_rows()` emits per preset `{key, name, strategy (display name), course_ref,
description, take_profit_pct, stop_loss_pct, drawdown_stop_pct}`; `agent.build_orchestrator_prompt`
renders briefing sections as compact JSON; `_AGENT_INSTRUCTIONS` tells the AI to match "trend and
breakout presets" vs "mean-reversion presets" to conditions. Strategy explanations live in
`strategy_bots/constants.STRATEGY_EXPLANATIONS` (one paragraph each, written for users).
Briefings are stored per run (JSON).

## Goals / Non-Goals

**Goals:** give the AI each strategy's explanation and a style family; document the preset list.

**Non-Goals:** per-preset performance statistics or backtests in the briefing; changing which
presets the AI may deploy; exposing styles in the public catalog API or UI (possible later).

## Decisions

1. **`StrategyStyle`** (`StrEnum`: trend, momentum, breakout, mean_reversion, regime_switching)
   and `STRATEGY_STYLES: dict[StrategyKey, StrategyStyle]` in `strategy_bots/constants.py`, beside
   the display names and explanations. Assignment:
   - trend — MA Crossover, ATR-Band Trend, ADX Trend, Heikin-Ashi Trend, HMA Trend, MA Ribbon,
     VAMA, Trend Confirmation, Bayesian Trend Predictor;
   - momentum — MACD Momentum;
   - breakout — Donchian Range Breakout, Volume Breakout;
   - mean_reversion — RSI Mean Reversion, Rolling-Average Reversion, Price Velocity Reversal,
     Multi-Signal Consensus;
   - regime_switching — Volatility Regime Switcher.
   A test asserts every `StrategyKey` has a style.
2. **`strategy_rows()`** returns, in catalog order of first use by a preset, `{key, name, style,
   explanation}` for each strategy referenced by a preset — once per strategy (19 entries vs 32
   presets; explanations are ~500 characters, so repeating them per preset would roughly double
   the section).
3. **`preset_rows()`** adds `strategy_key`, `style` and `params` (the preset's strategy params,
   already compact). Existing fields are unchanged, so stored briefings and the run audit view
   stay compatible.
4. **Prompt**: a `Strategies` section rendered right before `Presets`; instruction wording:
   "Each preset names its strategy; the Strategies section explains how each trades and its
   style. Match styles to conditions: trend, momentum and breakout presets suit names and
   sectors in an up-trend regime with healthy breadth; mean-reversion presets suit liquid names
   that have pulled back inside an intact longer-term trend; regime-switching presets suit names
   whose regime is unclear or changing."
5. **Prompt version** `ORCHESTRATOR_PROMPT_VERSION` 1 → 2, so each stored run records which prompt
   it used.
6. **Views requirement**: documents the existing `PresetCatalogPanel` as built; no code change.

## Risks / Trade-offs

- ~2–3k more input tokens per run (19 explanations) — cents per month at a daily cadence, shown
  in the orchestrator's AI cost.
- Style labels are a simplification (e.g. Keltner is a breakout within a trend family); the
  explanation carries the nuance.

## Migration Plan

None. New runs carry the new sections; stored briefings are untouched.

## Open Questions

None.
