## Context

The strategy-bot subsystem (see `backend/src/cadence/strategy_bots/`) uses a
three-layer model: pure `Strategy.evaluate(bars, position, params) -> Signal`
generators (layer 1), a registry mapping each `StrategyKey` to its implementation
+ params schema + required history (layer 3), and an engine that owns sizing,
TP/SL, the drawdown kill-switch, and the shared capital pool. MA Crossover and RSI
Mean Reversion are the strategies today. `bot_sessions.strategy_key` is a free-text
`Text` column and `strategy_params` is JSON, so new strategy keys/params are
additive with no migration. The build-a-bot form already renders the backend
strategy catalog in its `<select>` and preloads each strategy's reference-course
risk recipe, but its parameter inputs and submit payload branch only on strategy
key, not on a nested version. See proposal.md — Why.

The course source has three Donchian variants (Algo 25 Turtle rolling channel;
Algo 7 locked raw channel; Algo 8 locked ATR-padded channel). Algo 7 and Algo 8
differ only by whether the channel is padded by an ATR multiple, so they fold into
one "Locked" version with an `atr_padding_mult` knob.

## Goals / Non-Goals

**Goals:**
- Register a third strategy (Donchian Range Breakout) with the same purity and
  long-only contract as the existing strategies, reusing the registry/engine seams.
- Expose the course's three variants as **one** catalog strategy with a nested
  `version` selector, so the catalog stays legible and the shared indicator lives
  in one place.
- Make the build-a-bot form version-aware: render the selected version's inputs and
  preload its course risk recipe.

**Non-Goals:**
- No schema-driven/auto-generated form from the backend `params_schema` (a bounded,
  explicit per-version input block is used instead).
- No engine, sizing, guardrail, API-shape, bar-timeframe, or short-selling change.
- No cross-tick strategy state (the pure stateless `evaluate` contract is preserved).

## Decisions

- **One strategy + nested `version`, not three strategies.** A single
  `StrategyKey.DONCHIAN_BREAKOUT` with a `version: Literal['turtle', 'locked']`
  discriminator. Alternative (three top-level `StrategyKey`s) rejected: the three
  course algos share one indicator and would triplicate the catalog, the guide, and
  the form branches. The user explicitly chose the version-selector design.

- **Single params class, not a discriminated union.** One
  `DonchianBreakoutParams(StrategyParams)` holds `version` plus all four numeric
  fields, each with a default, an `after` validator enforcing the cross-field
  (`exit_period < entry_period`) and range rules, and a `required_history` property
  that branches on `version`. This keeps the existing single-params-class pattern
  (`extra='forbid'` inherited, rejecting typos) and the generic registry wiring
  unchanged. A Pydantic discriminated union was considered but rejected as
  heavier than the two-version surface warrants; the irrelevant version's numeric
  fields simply keep their defaults.

- **Bands exclude the current bar.** The Donchian high/low channel is computed over
  the `N` bars **preceding** the current bar (current excluded), upper band from
  `high`, lower band from `low`. If the current bar were included, its own high
  would cap the channel and a close could never exceed it — no breakout could ever
  trigger. This mirrors how the course scripts compare the latest tick against a
  window of prior ticks.

- **Turtle = rolling channel exit; Locked = engine-only exit.** Turtle enters on an
  `entry_period` high breakout and exits on an `exit_period` low breakdown — a
  genuine strategy-level exit (Algo 25). Locked enters on a (optionally ATR-padded)
  `channel_period` high breakout and, while in position, returns HOLD: it emits **no**
  channel exit, deferring entirely to the engine TP/SL bracket + drawdown
  kill-switch. **Why this faithfully reproduces "locked while in a trade":** the
  course's locked variants freeze the channel at entry and ride a fixed %-bracket
  out. A pure, stateless `evaluate` cannot carry a frozen band across ticks, but it
  does not need to — the band only matters for the *entry* decision (computed from
  current bars while flat), and once in a position every exit is a fixed bracket the
  engine already owns. So deferring all in-position exits to the engine reproduces
  the course behaviour with no cross-tick state.

- **Locked ATR = mean absolute successive close diff.** The ATR used for Locked's
  padding is a simple mean of `|close[i] - close[i-1]|` over the channel window,
  mirroring the course `calc_atr`. `atr_padding_mult = 0` ⇒ raw channel (Algo 7);
  `> 0` ⇒ padded channel (Algo 8, default 0.5). This avoids needing true-range
  (which would need the prior close threaded through) while matching the source.

- **Parameters & defaults.** `version` (`turtle`, default), `entry_period` (`int`,
  default 20, `ge=2`), `exit_period` (`int`, default 10, `ge=1`, `< entry_period`),
  `channel_period` (`int`, default 20, `ge=2`), `atr_padding_mult` (`float`,
  default 0.5, `ge=0`). `required_history = entry_period + 1` (turtle) or
  `channel_period + 1` (locked). Thresholds kept as free parameters so users can
  tune each bot.

- **Registration.** Add `StrategyKey.DONCHIAN_BREAKOUT = "donchian_breakout"` and
  its `STRATEGY_DISPLAY_NAMES` ("Donchian Range Breakout") / `STRATEGY_EXPLANATIONS`
  entries, then one `StrategyRegistration` in `_REGISTRY`. No other backend change —
  catalog reads, session creation, and the tick runner all resolve through the
  registry already.

- **Frontend version-aware params + per-version recipe.** In `BuildBotCard.tsx`,
  add a nested Version selector when Donchian is selected, with its own state and
  per-version parameter inputs (turtle: `entry_period`/`exit_period`; locked:
  `channel_period`/`atr_padding_mult`), branched `canSubmit` validation, and a
  branched `strategy_params` payload (`{ version, ... }`). Extend the existing
  course-recipe preload to the version axis: Turtle → TP off, SL off, drawdown 5;
  Locked → TP on 0.5%, SL on 2%, drawdown 5 (for Locked the engine bracket *is* the
  exit). Add a `donchian_breakout` descriptor to the `strategyCharts.ts` registry so
  the guide detail page renders an illustrative breakout chart; a missing descriptor
  already degrades gracefully to explanation-only.

## Risks / Trade-offs

- **Form coupling** → each new strategy (and now each version) touches
  `BuildBotCard.tsx`. Accepted for now; a schema-driven form remains a later
  refactor, explicitly a non-goal.
- **Locked exit lives entirely in the engine** → if a bot is created with Locked and
  TP/SL both off, it has no exit at all (only the drawdown kill-switch). Mitigation:
  the per-version recipe preloads Locked with TP/SL **on**, matching the course, so
  the default configuration always has an exit.
- **ATR approximation** → using close-diff ATR rather than true-range ATR is a minor
  divergence from a textbook ATR, but it matches the course `calc_atr` and keeps the
  function pure over closes. Accepted for fidelity to the source.
- **Current-bar exclusion is a modelling choice** → documented above; a reader
  expecting the current bar in the window might be surprised, so the reason strings
  and spec state the window is the *preceding* N bars.

## Migration Plan

No migration. `bot_sessions.strategy_key` is free-text `Text` and `strategy_params`
is JSON, so the new key and params persist with the existing schema. Rollback is
removing the registry entry; existing sessions are unaffected (no schema change).

## Open Questions

None.
