## Why

The strategy-bot subsystem ships only one strategy (MA Crossover), but its
three-layer design makes adding a strategy purely additive — implement a pure
signal generator and register one entry. RSI Mean Reversion (ported from course
Algo 16) is the agreed next bot on the roadmap: a counter-trend strategy that
complements the existing trend-follower, giving users a second, behaviourally
distinct rule to run.

## What Changes

- Add a new **RSI Mean Reversion** strategy to the strategy registry under a new
  `StrategyKey` (`rsi_mean_reversion`). It is a pure, long-only, single-symbol
  signal over OHLCV bars:
  - **ENTER_LONG** when flat and the latest Wilder-smoothed RSI is below the
    `oversold` threshold (buying an oversold dip);
  - **EXIT** when holding and RSI reverts above the `exit_level` threshold;
  - **HOLD** otherwise, and whenever there is insufficient history.
- Add its configurable parameters — `period` (default 14), `oversold` (default
  30), `exit_level` (default 50) — as a new `StrategyParams` subclass with bound
  validation (`oversold < exit_level`), `required_history = period + 1`.
- Register its human-facing display name and plain-language explanation so it
  appears in the strategy catalog, the build-a-bot picker, and the per-strategy
  guide.
- Make the build-a-bot form **strategy-aware**: render the selected strategy's
  own parameter inputs (RSI's period/oversold/exit_level vs. MA Crossover's
  fast/slow periods) and submit the matching `strategy_params`.
- Add the RSI strategy to the per-strategy guide (index card + detail page) with
  an illustrative client-side chart.
- The course strategy's short leg (enter short when RSI > 70) is **dropped**
  (Cadence is long-only), and its take-profit / stop-loss / drawdown exits are
  **not** reimplemented — the existing engine guardrails already own sizing,
  TP/SL, and the drawdown kill-switch.

## Capabilities

### New Capabilities

- _None._

### Modified Capabilities

- `strategy-bots`: ADD a requirement for the RSI Mean Reversion strategy (its
  entry/exit/hold signal rules, parameters, long-only behaviour, and required
  history). The existing registry / MA Crossover requirement is unchanged — RSI
  is registered alongside it, not in place of it.

## Impact

- **Backend** (`backend/src/cadence/strategy_bots/`): new `rsi_mean_reversion.py`
  (strategy + params); new `StrategyKey.RSI_MEAN_REVERSION` and its
  `STRATEGY_DISPLAY_NAMES` / `STRATEGY_EXPLANATIONS` entries in `constants.py`; a
  new `StrategyRegistration` in `registry.py`. No engine, sizing, guardrail, API,
  or schema changes. `strategy_key` is a free-text column, so **no Alembic
  migration** is required.
- **Frontend** (`frontend/src/pages/bots/`): `BuildBotCard.tsx` gains
  strategy-aware parameter inputs and submission; `strategyCharts.ts` gains an
  RSI chart descriptor; the strategy guide detail page renders RSI. The strategy
  `<select>` already enumerates the backend catalog, so RSI appears there
  automatically.
- **No change** to `BOT_SIGNAL_BAR_TIMEFRAME` (stays intraday 5Min), the MA
  Crossover strategy, short-selling (still unsupported), or any backtest tooling
  (none exists).
