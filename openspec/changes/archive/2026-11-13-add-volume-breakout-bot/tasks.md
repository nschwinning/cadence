## 1. Strategy

- [x] 1.1 Create `strategy_bots/volume_breakout.py` (`VolumeBreakoutParams`, `VolumeBreakoutStrategy`, VROC / ADL helpers); wire `StrategyKey.VOLUME_BREAKOUT` ("Volume Breakout"), explanation, registry; verify with pytest (Spike: breakout + spike → enter, breakout without spike → hold, breakdown + spike while holding → exit, holding otherwise → hold; VROC: priming then first breakout → enter, no priming in window → hold, range already broken → hold, negative VROC while holding → exit, non-positive volume → no priming; Chaikin: zero cross up → enter, oscillator < 0 holding → exit, offset invariance; insufficient history per version; never short; params validation).
- [x] 1.2 Add the four presets (`volume_spike_algo34` default, `volume_spike_simple_algo34`, `vroc_breakout_algo46`, `chaikin_oscillator_algo45`); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: Volume Breakout version select + per-version fields, validation and payload; verify with vitest (preset fills values and submits the version's params; switching version shows its fields; chaikin_fast ≥ chaikin_slow blocks submit) and update the preset-list pins.
- [x] 2.2 `volumeBreakoutChart.ts` registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: Volume Breakout shipped (15 of 16); Tier 3 complete; Algo 45's fake high/low resolved by real bars.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-volume-breakout-bot --strict` passes.
