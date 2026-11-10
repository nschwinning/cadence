## 1. Preset catalog (backend)

- [x] 1.1 Add `BotOrigin` StrEnum (`MANUAL = "manual"`) to `strategy_bots/constants.py` and `UnknownPresetError` to `strategy_bots/errors.py`. Verify: mypy clean.
- [x] 1.2 Create `strategy_bots/presets.py` with the frozen `BotPreset` dataclass, the four course presets (`ma_crossover_algo6`, `rsi_mean_reversion_algo16`, `donchian_turtle_algo25` default, `donchian_smart_range_algo8`) using fractions for risk values, plus `list_presets()` and `get_preset(key)`. Verify: new `tests/test_strategy_bots_presets.py` asserts unique keys, every preset's params parse via `registry.get_strategy(...).parse_params`, exactly one default per registered strategy, `get_preset` raises `UnknownPresetError` for an unknown key, and each preset's values match the spec's course recipe table.

## 2. Session provenance (model + migration)

- [x] 2.1 Add `preset_key: str | None`, `preset_customized: bool` (server default false), and `origin: str` (server default `'manual'`) to `BotSession` in `models.py`. Verify: mypy clean.
- [x] 2.2 Generate the Alembic migration (`cd backend && uv run alembic revision --autogenerate -m "bot session preset provenance"`), review that it only adds the three columns with server defaults, and round-trip it against the 5435 test DB. Verify: `upgrade head` → `downgrade -1` → `upgrade head` succeeds; tear the test DB container down afterward.

## 3. Preset-aware creation (service)

- [x] 3.1 Extend `service.create_bot_session` with `preset_key` and the `_UNSET` sentinel for the four overridable values (design decision 3): resolve the preset, enforce strategy-key match or infer it, fill unsupplied values from the preset, and leave the no-preset path untouched. Verify: unit tests — preset with no overrides uses the preset's strategy/params/TP/SL/drawdown; supplied value overrides; explicit `None` turns a preset's TP off; unknown preset → `UnknownPresetError`; mismatched strategy → `InvalidBotConfigError`; neither strategy nor preset → `InvalidBotConfigError`.
- [x] 3.2 Compute and store `preset_customized` on normalized values (`parse_params(...).model_dump()` + `math.isclose` for risk) and set `origin = BotOrigin.MANUAL`. Verify: unit tests — values equal to the preset → not customized (including a Donchian dict that omits inactive-version fields); one differing param or risk value → customized; no preset → `preset_key` None, not customized, origin manual.

## 4. API

- [x] 4.1 Add `BotPresetRead` and `GET /bots/presets` (catalog order); make `BotSessionCreateRequest.strategy_key` optional and add `preset_key`; pass only `model_fields_set` overridable fields as overrides when a preset is given; map `UnknownPresetError` → 422; add `preset_key` / `preset_customized` / `origin` to `BotSessionRead`. Verify: API tests — presets list returns all four with fields + default flags; create from preset without overrides → 201 with `preset_key` set, `preset_customized` false, `origin` "manual"; create with an override → customized true; unknown preset → 422; mismatched strategy → 422; existing create tests (no preset) still pass unchanged.

## 5. Frontend

- [x] 5.1 Add `BotPreset` type, `preset_key` to `BotSessionCreateRequest`, provenance fields to `BotSession` in `types/api.ts`; add `fetchPresets` + `usePresets` to `api/bots.ts`. Verify: `npx tsc --noEmit` clean.
- [x] 5.2 Refactor `BuildBotCard.tsx`: remove `STRATEGY_RISK_DEFAULTS` / `DONCHIAN_VERSION_RISK_DEFAULTS`, add a pure preset→form-state helper, apply the default preset on open and on strategy change, apply the version's preset on Donchian version change, derive a "Customized" marker by comparing current values to the applied preset, disable submit until presets load, and send `preset_key` in the payload. Verify: vitest — form opens with the MA Crossover preset values; switching to RSI applies its preset; switching Donchian version to Locked applies the Algo 8 preset; editing a value shows "Customized" and reverting clears it; submit payload includes `preset_key`; existing BuildBotCard tests updated to mock `/bots/presets` and still pass.
- [x] 5.3 Show provenance on `BotSessionPage.tsx` (preset display name via `usePresets`, "customized" mark, "Custom configuration" when no preset, raw key fallback when the preset is unknown). Verify: vitest — unchanged preset, customized preset, no preset, and unknown-key fallback each render the expected text.

## 6. Verification gates

- [x] 6.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` against the 5435 Postgres test DB. Verify: all green; then tear the test DB container down.
- [x] 6.2 Frontend: `cd frontend && npx vitest run && npx tsc --noEmit`. Verify: all green.
- [x] 6.3 `openspec validate add-bot-preset-catalog --strict`. Verify: passes.
