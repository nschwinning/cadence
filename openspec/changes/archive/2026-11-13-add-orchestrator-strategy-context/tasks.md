## 1. Strategy styles

- [x] 1.1 Add `StrategyStyle` and `STRATEGY_STYLES` to `strategy_bots/constants.py`; verify with a pytest that every `StrategyKey` has a style and the assignment matches the design.

## 2. Briefing and prompt

- [x] 2.1 `briefing.py`: `strategy_rows()` (once per strategy used by a preset, catalog order) and `preset_rows()` gains `strategy_key`, `style`, `params`; `build_briefing` adds `"strategies"`; verify with pytest (one row per used strategy with style + explanation; presets carry key/style/params; strategies referenced by presets all present).
- [x] 2.2 `agent.py`: render a `Strategies` section before `Presets`; update the instructions' matching guideline; verify with the agent prompt tests (section present and ordered, instruction mentions styles).

## 3. Spec-only

- [x] 3.1 The views requirement documents the existing preset catalog list (no code change); confirm `OrchestratorsPage.test.tsx` already covers the delta's scenario.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 `openspec validate add-orchestrator-strategy-context --strict` passes.
