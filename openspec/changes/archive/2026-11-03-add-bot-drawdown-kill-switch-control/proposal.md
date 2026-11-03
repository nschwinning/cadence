## Why

The strategy-bot drawdown kill-switch is always on (every bot session stores a
non-null `drawdown_stop_pct`), but the Build-a-bot form never lets the user set it. The
form's submit payload sends `take_profit_pct` and `stop_loss_pct` yet omits
`drawdown_stop_pct`, so every bot silently falls back to the backend default
`BOT_DRAWDOWN_STOP_PCT = 0.25` (25%) and the user cannot change it. This blocks building
a bot that matches a desired risk profile — e.g. the course's MA-Crossover bot, which
uses a 5% drawdown kill-switch. The backend, API, and TypeScript types already accept a
per-session `drawdown_stop_pct`; only the form is missing the control.

## What Changes

- Add a **"Drawdown kill-switch (%)"** control to the bot build form, entered in friendly
  percent units (like the existing risk %, max-position %, take-profit %, and stop-loss %
  fields) and converted to a fraction (÷100) on submit into `drawdown_stop_pct`.
- The control is a **required threshold**, not an enable/disable toggle — the kill-switch
  is always on. It defaults to the configured default (shown as `25`) so leaving it
  untouched preserves today's behavior; the user can lower it (e.g. to `5`).
- Validate the entered percent to `0 < pct < 100` (fraction `0 < x < 1`, matching the
  API's `gt=0` and the fraction semantics); an out-of-range value shows an inline invalid
  hint and blocks submit, consistent with the form's other numeric fields.
- Always include `drawdown_stop_pct` in the create request.

No backend, API, schema, or migration change — the backend already resolves a
per-session threshold and falls back to the configured default when none is sent. The
default `BOT_DRAWDOWN_STOP_PCT` is unchanged. Take-profit / stop-loss, sizing, strategy
parameters, and the strategy catalog are unchanged, and the kill-switch stays always-on.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `app-shell`: The "Strategy bots navigation entry and views" requirement changes so the
  dedicated bot build form also lets the user configure the (always-on) drawdown
  kill-switch threshold, defaulting to the configured default, sent as `drawdown_stop_pct`
  on creation.

## Impact

- **Frontend only.** `frontend/src/pages/bots/BuildBotCard.tsx` adds a drawdown
  kill-switch percent field (state, a `NumberField`, validation, and inclusion of
  `drawdown_stop_pct` in the `BotSessionCreateRequest` payload). The TS type
  `BotSessionCreateRequest.drawdown_stop_pct` already exists.
- No backend, API, database, or dependency changes.
