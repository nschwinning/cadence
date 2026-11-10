## Context

Course recipes currently live only in `frontend/src/pages/bots/BuildBotCard.tsx`
(`STRATEGY_RISK_DEFAULTS`, `DONCHIAN_VERSION_RISK_DEFAULTS`, plus course-seeded
`useState` defaults for each strategy's parameters). Strategy parameter schemas
(`MACrossoverParams`, `RsiMeanReversionParams`, `DonchianBreakoutParams`) already default
to course values, but risk controls do not: the backend falls back to
`settings.BOT_DRAWDOWN_STOP_PCT = 0.25` and no take-profit/stop-loss. Risk controls travel
as **fractions** (`take_profit_pct=0.01` means 1%); the form converts percent input ÷100.
The form always submits `strategy_params`, `take_profit_pct`, `stop_loss_pct` (null when
off) and `drawdown_stop_pct`.

## Goals / Non-Goals

**Goals:**
- A single backend source of truth for presets that both the form and a future
  orchestrator read.
- Provenance (`preset_key`, `preset_customized`, `origin`) stored at creation so it stays
  correct even if a preset's values change later.
- Zero behavior change for requests without `preset_key`.

**Non-Goals:**
- Persisting presets in the database or editing them at runtime.
- Presets carrying sizing, capital, tickers, or benchmark.
- Any orchestrator logic, scheduling, or new `origin` values beyond `manual`.

## Decisions

**1. Presets are a code-defined catalog (`strategy_bots/presets.py`), not a DB table.**
A frozen `BotPreset` dataclass (`key`, `display_name`, `description`, `course_ref`,
`strategy_key: StrategyKey`, `strategy_params: dict`, `take_profit_pct: float | None`,
`stop_loss_pct: float | None`, `drawdown_stop_pct: float`, `is_default: bool`) in an
ordered tuple, with `list_presets()` and `get_preset(key)` (raises a new
`UnknownPresetError`). This mirrors `registry.py`: presets are versioned with the strategy
code that interprets them, reviewed in diffs, and need no migration to add. A DB table was
rejected because nothing edits presets at runtime and it would split the source of truth
from the strategy schemas. Preset keys are stable snake_case:
`ma_crossover_algo6`, `rsi_mean_reversion_algo16`, `donchian_turtle_algo25`,
`donchian_smart_range_algo8`.

**2. Catalog integrity is enforced by tests, not at import time.** Unit tests assert every
preset's params parse through `registry.get_strategy(...).parse_params`, keys are unique,
and each registered strategy has exactly one default. Import-time validation was rejected
because a bad preset would crash app startup instead of failing CI.

**3. "Supplied" means present in the request, including explicit `null`.** The router
passes only fields in `BotSessionCreateRequest.model_fields_set` that are preset-overridable
(`strategy_params`, `take_profit_pct`, `stop_loss_pct`, `drawdown_stop_pct`) as overrides.
An explicit `null` for TP/SL therefore turns a preset's bracket off, while an omitted field
inherits it. The service takes an explicit sentinel (`_UNSET`) for these parameters only
when `preset_key` is given; without a preset, the existing `None` semantics are unchanged.
Merging `strategy_params`: the supplied dict **replaces** the preset's dict entirely (then
schema defaults fill gaps). A key-wise merge was rejected because the form always sends a
complete version-specific dict, and replacement keeps "what you sent is what runs" simple.

**4. `strategy_key` becomes optional on the create request.** When `preset_key` is set
and `strategy_key` is omitted, the preset's strategy is used; when both are set they must
match (`InvalidBotConfigError` → 422, matching existing config errors). When neither is
set → 422. Unknown preset → `UnknownPresetError` → 422 (same mapping as an unknown
strategy).

**5. Customized is computed once, at creation, on normalized values.** Compare
`parse_params(effective).model_dump()` with `parse_params(preset.strategy_params).model_dump()`
(so inactive Donchian-version fields and schema defaults compare equal), and compare the
three risk fields with `math.isclose` (both `None` = equal; one `None` = different). Stored
as `preset_customized: bool` (non-null, default false). Computing on read was rejected
because a later preset edit would retroactively flip historical sessions.

**6. Origin is a `BotOrigin` StrEnum stored as text** (`manual` only), column non-null with
server default `'manual'` so existing rows backfill without a data migration. Free text
mirrors how `stop_reason` and `strategy_key` are stored.

**7. Read endpoint `GET /bots/presets`** returns `BotPresetRead` items in catalog order,
risk values as fractions (same unit as the session fields). `BotSessionRead` gains
`preset_key`, `preset_customized`, `origin`.

**8. Frontend.** `usePresets()` (TanStack Query, long `staleTime`) feeds `BuildBotCard`.
The hardcoded recipe tables are removed; a pure helper maps a preset → form state
(fractions ×100 → percent strings; TP/SL `null` → toggle off with the previous percent kept
as the field's placeholder value). The form tracks `appliedPresetKey`; strategy change applies
that strategy's default preset, Donchian version change applies the preset whose
`strategy_params.version` matches. A "Customized" marker is derived by comparing current
form values to the applied preset (not by a sticky dirty flag), so reverting an edit clears
it. Until presets load, the form shows its existing loading state for the strategies query;
submit is disabled while presets are pending. The payload sends `preset_key` plus all
values; the backend's comparison is authoritative for `preset_customized`. The detail page
resolves the preset display name via `usePresets()` and falls back to the raw key if a
preset was later removed.

## Risks / Trade-offs

- [Float drift between the form's percent→fraction conversion and preset fractions could
  falsely flag "customized"] → `math.isclose` on the backend; the form compares in percent
  strings parsed to numbers with the same tolerance.
- [A preset removed from the catalog leaves sessions pointing at an unknown key] → store the
  key only; the detail view falls back to showing the key. Presets should be added, not
  removed, and keys never reused.
- [The form now depends on a second query before it can submit] → presets are static and
  cached with a long `staleTime`; a load failure shows an error and keeps submit disabled
  rather than silently using stale client values.
- [`strategy_key` becoming optional widens the request contract] → validated server-side;
  existing clients that always send it are unaffected.

## Migration Plan

One Alembic revision on `bot_sessions`: add `preset_key TEXT NULL`,
`preset_customized BOOLEAN NOT NULL DEFAULT false`, `origin TEXT NOT NULL DEFAULT 'manual'`.
Existing rows become "no preset, not customized, manual" — which is accurate. Downgrade drops
the three columns. Verify upgrade → downgrade → upgrade against the 5435 test DB, then tear
the container down.
