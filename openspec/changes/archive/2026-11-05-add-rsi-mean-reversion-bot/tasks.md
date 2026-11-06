## 1. Backend — RSI strategy + params

- [x] 1.1 Add `rsi_mean_reversion.py` under `backend/src/cadence/strategy_bots/`
  with `RsiMeanReversionParams(StrategyParams)` — `period: int` (default 14,
  `ge=1`), `oversold: float` (default 30, `ge=0, le=100`), `exit_level: float`
  (default 50, `ge=0, le=100`), an `after` validator raising when
  `oversold >= exit_level`, and `required_history` property returning `period + 1`.
  Verify: new unit tests instantiate defaults, reject `oversold >= exit_level`,
  reject out-of-range thresholds, and reject an unknown key (`extra='forbid'`).
- [x] 1.2 In the same module add `RsiMeanReversionStrategy` implementing the
  `Strategy` protocol: compute Wilder-smoothed RSI of bar closes; return
  ENTER_LONG when flat and latest RSI `< oversold`, EXIT when holding and latest
  RSI `> exit_level`, else HOLD; return HOLD when `len(bars) < period + 1`; raise
  `TypeError` if handed the wrong params type (mirror `ma_crossover.py`). Each
  non-HOLD `Signal` carries a reason naming the RSI value/threshold. Verify: unit
  tests assert Wilder RSI on a known close series, and the ENTER/EXIT/HOLD/no-short
  transitions.

## 2. Backend — registration

- [x] 2.1 Add `StrategyKey.RSI_MEAN_REVERSION = "rsi_mean_reversion"` to
  `constants.py`, plus its `STRATEGY_DISPLAY_NAMES` ("RSI Mean Reversion") and
  `STRATEGY_EXPLANATIONS` (plain-language: buys oversold dips when RSI is below the
  oversold level, exits as RSI reverts above the exit level, long-only, engine
  applies TP/SL/drawdown) entries. Verify: `mypy`/`ruff` clean; constants import.
- [x] 2.2 Register a `StrategyRegistration` for the RSI strategy in `registry.py`
  `_REGISTRY`. Verify: a unit test asserts `get_strategy("rsi_mean_reversion")`
  resolves it and `list_strategies()` includes it with display name, explanation,
  and params schema.
- [x] 2.3 Confirm no migration is needed: `bot_sessions.strategy_key` is a
  free-text `Text` column, so the new key needs no Alembic change. Verify: inspect
  `strategy_bots/models.py` (column is `Mapped[str] = mapped_column(Text, ...)`)
  and a session-create test with `strategy_key="rsi_mean_reversion"` + valid RSI
  params succeeds end-to-end through the service.

## 3. Frontend — strategy-aware build form

- [x] 3.1 In `BuildBotCard.tsx` add RSI parameter state (period/oversold/exit_level
  with defaults 14/30/50) and render the "Strategy parameters" block conditionally
  on the selected `strategyKey`: MA Crossover shows fast/slow SMA; RSI shows
  period/oversold/exit_level. Verify: a Vitest test selects the RSI strategy and
  asserts its three inputs appear (and the SMA inputs do not).
- [x] 3.2 Branch `handleSubmit` to build `strategy_params` for the selected
  strategy (`{ period, oversold, exit_level }` for RSI) and branch `canSubmit`
  validation per strategy (period `>= 1`, thresholds in 0–100, `oversold <
  exit_level`). Verify: a Vitest test fills RSI params, submits, and asserts the
  create request carries `strategy_key: "rsi_mean_reversion"` and the RSI
  `strategy_params`; invalid bands disable submit.

## 4. Frontend — strategy guide

- [x] 4.1 Add an `rsi_mean_reversion` descriptor to the `strategyCharts.ts`
  registry (an illustrative RSI mean-reversion chart option + aria-label). Verify:
  a Vitest test asserts `getStrategyChart("rsi_mean_reversion")` returns a
  descriptor and that the strategy detail page renders the RSI explanation + chart.

## 5. Verification gates

- [x] 5.1 Backend gates green: `cd backend && uv run ruff check . && uv run mypy
  src/cadence && uv run pytest`.
- [x] 5.2 Frontend gates green: `cd frontend && npx vitest run && npx tsc --noEmit`.
- [x] 5.3 `openspec validate add-rsi-mean-reversion-bot --strict` passes.
