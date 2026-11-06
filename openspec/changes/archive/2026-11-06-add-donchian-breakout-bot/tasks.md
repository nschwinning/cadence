## 1. Backend — Donchian strategy + params

- [x] 1.1 Add `donchian_breakout.py` under `backend/src/cadence/strategy_bots/`
  with `DonchianBreakoutParams(StrategyParams)` — `version: Literal['turtle',
  'locked']` (default `'turtle'`), `entry_period: int` (default 20, `ge=2`),
  `exit_period: int` (default 10, `ge=1`), `channel_period: int` (default 20,
  `ge=2`), `atr_padding_mult: float` (default 0.5, `ge=0`), an `after` validator
  raising when `exit_period >= entry_period`, and a `required_history` property
  returning `entry_period + 1` for turtle and `channel_period + 1` for locked.
  Verify: new unit tests instantiate defaults, reject `exit_period >= entry_period`,
  reject out-of-range periods / negative padding, reject an unknown key
  (`extra='forbid'`), reject an invalid `version`, and assert `required_history`
  branches on version.
- [x] 1.2 In the same module add pure helpers for the Donchian bands (highest high
  / lowest low over the `N` bars **preceding** the current bar) and the simple ATR
  (mean absolute successive close diff over the channel window), then
  `DonchianBreakoutStrategy` implementing the `Strategy` protocol: for the Turtle
  version return ENTER_LONG when flat and the latest close is above the previous
  `entry_period`-bar high, EXIT when holding and the latest close is below the
  previous `exit_period`-bar low, else HOLD; for the Locked version return
  ENTER_LONG when flat and the latest close is above the padded `channel_period`-bar
  high, else HOLD (no channel exit — exits deferred to the engine); return HOLD when
  `len(bars) < required_history`; raise `TypeError` if handed the wrong params type
  (mirror `ma_crossover.py` / `rsi_mean_reversion.py`). Each non-HOLD `Signal`
  carries a reason naming the breakout level. Verify: unit tests assert the band/ATR
  helpers on a known series, and the ENTER/EXIT/HOLD/no-short/insufficient-history
  transitions for BOTH versions (incl. Locked HOLD-in-position defers exit, and raw
  band when `atr_padding_mult = 0`).

## 2. Backend — registration

- [x] 2.1 Add `StrategyKey.DONCHIAN_BREAKOUT = "donchian_breakout"` to
  `constants.py`, plus its `STRATEGY_DISPLAY_NAMES` ("Donchian Range Breakout") and
  `STRATEGY_EXPLANATIONS` (plain-language: enters long on an upward channel
  breakout; Turtle exits on a channel-low breakdown while Locked defers exits to the
  engine; describe the ATR-padding knob; long-only; engine applies TP/SL/drawdown)
  entries. Verify: `mypy`/`ruff` clean; constants import.
- [x] 2.2 Register a `StrategyRegistration` for the Donchian strategy in
  `registry.py` `_REGISTRY` (import `DonchianBreakoutParams` /
  `DonchianBreakoutStrategy`; display name + explanation from constants). Verify: a
  unit test asserts `get_strategy("donchian_breakout")` resolves it and
  `list_strategies()` includes it with display name, explanation, and params schema.
- [x] 2.3 Confirm no migration is needed: `bot_sessions.strategy_key` is a free-text
  `Text` column and `strategy_params` is JSON, so the new key/params need no Alembic
  change. Verify: a session-create test through the service with
  `strategy_key="donchian_breakout"` + valid **turtle** params AND valid **locked**
  params both succeed end-to-end.

## 3. Frontend — version-aware build form

- [x] 3.1 In `BuildBotCard.tsx` add Donchian to `STRATEGY_RISK_DEFAULTS`, add an
  `isDonchian` flag, nested `version` state, and per-version param state (turtle:
  `entry_period`/`exit_period` default 20/10; locked: `channel_period`/
  `atr_padding_mult` default 20/0.5). Render a nested "Version" selector (Turtle
  rolling / Locked channel) followed by the selected version's `NumberField`s;
  hide the MA/RSI inputs when Donchian is selected. Verify: a Vitest test selects
  Donchian, asserts the Version selector + the active version's inputs appear (and
  the SMA/RSI inputs do not), and that switching version swaps the inputs.
- [x] 3.2 Add a per-version course-recipe preload: when the version changes (and on
  selecting Donchian), re-apply the version's risk recipe — Turtle → TP off, SL off,
  drawdown 5; Locked → TP on 0.5%, SL on 2%, drawdown 5 — extending the existing
  `handleStrategyChange` preload. Verify: a Vitest test asserts switching to Locked
  turns TP/SL on with 0.5%/2% and switching to Turtle turns them off.
- [x] 3.3 Branch `canSubmit` validation per version (periods `>= 2`/`>= 1`,
  `exit_period < entry_period`, `atr_padding_mult >= 0`) producing
  `donchianParamsValid` + per-field `*Invalid` flags, and branch the
  `strategy_params` payload builder to emit `{ version, ...turtle-or-locked fields }`.
  Verify: a Vitest test fills each version's params, submits, and asserts the create
  request carries `strategy_key: "donchian_breakout"` and the correct
  `{ version, ... }` `strategy_params`; invalid params disable submit.

## 4. Frontend — strategy guide

- [x] 4.1 Add `donchianChart.ts` (`buildDonchianChartOption()`, an illustrative
  synthetic breakout-above-the-upper-channel chart, mirroring `rsiChart.ts`) and
  register a `donchian_breakout` descriptor in the `strategyCharts.ts` registry.
  Verify: a Vitest test asserts `getStrategyChart("donchian_breakout")` returns a
  descriptor and that the strategy detail page renders the Donchian explanation +
  chart.

## 5. Verification gates

- [x] 5.1 Backend gates green: `cd backend && uv run ruff check . && uv run mypy
  src/cadence && uv run pytest` (needs the Postgres test DB on port 5435 — start
  Docker only for this run and tear it down afterwards).
- [x] 5.2 Frontend gates green: `cd frontend && npx vitest run && npx tsc --noEmit`.
- [x] 5.3 `openspec validate add-donchian-breakout-bot --strict` passes.
