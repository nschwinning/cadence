## Why

The strategy-bot subsystem's three-layer design makes adding a strategy purely
additive — implement a pure signal generator and register one entry. **Donchian
Range Breakout** (ported from course Algos 25/7/8) is the agreed next bot on the
roadmap (Tier-1 #2): a channel-breakout trend strategy that complements the
existing MA Crossover trend-follower and the RSI counter-trend bot. The course
has three Donchian variants that share one underlying indicator, so rather than
clutter the catalog with three near-duplicate strategies we expose them as **one**
strategy with a nested **Version** selector.

## What Changes

- Add a new **Donchian Range Breakout** strategy to the strategy registry under a
  new `StrategyKey` (`donchian_breakout`). It is a pure, long-only, single-symbol
  signal over OHLCV bars that enters long on an upward channel breakout. It exposes
  a `version` discriminator with two variants of the same Donchian-channel idea:
  - **Turtle rolling channel** (ported from Algo 25): **ENTER_LONG** when flat and
    the latest close breaks **above** the highest high of the previous `entry_period`
    bars; **EXIT** when holding and the latest close breaks **below** the lowest low
    of the previous `exit_period` bars; **HOLD** otherwise.
  - **Locked channel** (folds Algo 7 + Algo 8): **ENTER_LONG** when flat and the
    latest close breaks above the highest high of the previous `channel_period` bars
    padded outward by `atr_padding_mult × ATR` (padding `0` ⇒ Algo 7 raw channel,
    `> 0` ⇒ Algo 8 false-breakout buffer); while holding it **HOLD**s — all exits
    are deferred to the engine's TP/SL bracket + drawdown kill-switch (faithfully
    reproducing the course's "locked while in a trade" behaviour without needing
    cross-tick strategy state).
- Add its configurable parameters as a new `StrategyParams` subclass: `version`
  (`'turtle' | 'locked'`, default `'turtle'`), `entry_period` (default 20),
  `exit_period` (default 10, must be `< entry_period`), `channel_period`
  (default 20), `atr_padding_mult` (default 0.5). `required_history` branches on
  version (`entry_period + 1` turtle, `channel_period + 1` locked).
- Register its human-facing display name and plain-language explanation so it
  appears in the strategy catalog, the build-a-bot picker, and the per-strategy
  guide.
- Make the build-a-bot form **version-aware**: when Donchian is selected, render a
  nested Version selector plus the chosen version's parameter inputs, and preload
  each version's reference-course risk recipe (Turtle → TP/SL off, drawdown 5;
  Locked → TP 0.5% / SL 2% on, drawdown 5), extending the existing per-strategy
  course-recipe preload to the version axis.
- Add the Donchian strategy to the per-strategy guide (index card + detail page)
  with an illustrative client-side chart.
- The course strategies' short legs are **dropped** (Cadence is long-only), and
  their ATR hard-stop / fixed %-bracket exits / ATR risk sizing / pyramiding are
  **not** reimplemented in the strategy — the existing engine guardrails already
  own sizing, TP/SL, and the drawdown kill-switch.

## Capabilities

### New Capabilities

- _None._

### Modified Capabilities

- `strategy-bots`: ADD a requirement for the Donchian Range Breakout strategy (its
  two versions' entry/exit/hold signal rules, parameters + version discriminator,
  long-only behaviour, and required history). The existing registry / MA Crossover
  / RSI requirements are unchanged — Donchian is registered alongside them.

## Impact

- **Backend** (`backend/src/cadence/strategy_bots/`): new `donchian_breakout.py`
  (strategy + params + pure band/ATR helpers); new `StrategyKey.DONCHIAN_BREAKOUT`
  and its `STRATEGY_DISPLAY_NAMES` / `STRATEGY_EXPLANATIONS` entries in
  `constants.py`; a new `StrategyRegistration` in `registry.py`. No engine, sizing,
  guardrail, API, or schema changes. `strategy_key` is a free-text column and
  `strategy_params` is JSON, so **no Alembic migration** is required.
- **Frontend** (`frontend/src/pages/bots/`): `BuildBotCard.tsx` gains the nested
  Version selector, version-aware parameter inputs + submission, and per-version
  recipe preload; `donchianChart.ts` + `strategyCharts.ts` gain a Donchian chart
  descriptor; the strategy guide detail page renders Donchian. The strategy
  `<select>` already enumerates the backend catalog, so Donchian appears there
  automatically.
- **No change** to `BOT_SIGNAL_BAR_TIMEFRAME`, the MA Crossover / RSI strategies,
  short-selling (still unsupported), the engine, sizing, the service tick runner,
  the generic catalog/create routes, or any backtest tooling (none exists).
