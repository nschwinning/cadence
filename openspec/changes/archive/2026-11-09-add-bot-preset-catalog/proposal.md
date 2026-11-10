## Why

The long-term goal is an AI orchestrator that deploys and stops strategy bots on its own,
choosing only from a fixed set of vetted configurations (the reference-course recipes),
while manual bot creation keeps full freedom over every parameter. Today those course
recipes exist only as hardcoded defaults inside the frontend build form, so the backend
has no notion of a "preset" an orchestrator could pick from, and a session does not record
whether it was built from a course recipe or tuned by hand. This change makes presets a
first-class backend catalog and records each session's provenance, which both the manual
form and the future orchestrator need.

## What Changes

- Add a backend **bot preset catalog**: named, fixed configurations, each binding one
  registered strategy to its course-recipe strategy parameters and risk controls
  (take-profit, stop-loss, drawdown kill-switch), with a display name, a course reference,
  and a short description. Every preset's parameters are validated against its strategy's
  parameter schema.
- Seed the catalog 1:1 with the recipes the build form already uses:
  MA Crossover (Algo 6), RSI Mean Reversion (Algo 16), Donchian Turtle (Algo 25), and
  Donchian Locked / Smart Range Breakout (Algo 8). Each strategy has exactly one
  **default preset**.
- Add a read endpoint listing the presets.
- Session creation accepts an optional **preset key**. Fields the request does not supply
  are filled from the preset; fields it does supply override it. The session records the
  preset it started from and whether its effective configuration was **customized** away
  from that preset. Capital, traded assets, benchmark, label, and sizing stay deployment
  choices and are not part of a preset.
- Each session records its **origin** (only `manual` exists in this change; the future
  orchestrator adds its own value).
- Session reads expose the preset key, the customized flag, and the origin.
- The build form loads presets from the API instead of its hardcoded recipe tables. It
  still opens preconfigured with the selected strategy's default preset, switching strategy
  (or Donchian version) applies the matching preset, and every field stays editable. Editing
  a preset-derived field marks the configuration as customized in the form.
- The bot detail view shows the session's provenance (the preset name, marked "customized"
  when it was changed, or "Custom" when no preset was used).
- New migration adding the nullable `preset_key`, the `preset_customized` flag, and `origin`
  (defaulted to `manual` for existing rows) to `bot_sessions`.

## Capabilities

### New Capabilities

<!-- None: presets are part of the strategy-bot domain. -->

### Modified Capabilities

- `strategy-bots`: adds the preset catalog requirement, extends the session lifecycle
  requirement so creation can start from a preset and records the preset key, customized
  flag, and origin, and adds the preset-driven build-form and detail-view provenance
  requirements.

## Impact

- **Backend**: new `strategy_bots/presets.py` (catalog + lookup), `constants.py`
  (`BotOrigin`), `models.py` (three `BotSession` columns), `service.create_bot_session`
  (preset resolution + customized detection), `api/schemas.py` (preset read schema; create
  request `preset_key`; session read fields), `api/routers/bots.py` (`GET /bots/presets`),
  new Alembic migration.
- **Frontend**: `types/api.ts`, `api/bots.ts` (`usePresets`), `BuildBotCard.tsx` (presets
  from the API replace `STRATEGY_RISK_DEFAULTS` / `DONCHIAN_VERSION_RISK_DEFAULTS`),
  `BotSessionPage.tsx` (provenance display).
- **Behavior unchanged**: tick engine, sizing, valuation, KPIs, kill-switch, and every
  strategy's signal logic. Requests without `preset_key` behave exactly as today (recorded
  as custom, origin manual).
- **Out of scope**: the AI orchestrator itself; new strategies (Rolling-Average Reversion
  ships next, with its own presets); per-preset sizing or capital recipes; editing presets
  from the UI.
