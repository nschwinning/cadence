## Context

`frontend/src/pages/bots/BuildBotCard.tsx` is the dedicated bot build form. Today it has
state + controls for strategy key, tickers / whole-universe, capital, benchmark, label,
`fast_period` / `slow_period`, sizing (`sizing_method`, `risk_pct`, `atr_period`, `atr_k`,
`max_position_pct`, `max_positions`), and optional take-profit / stop-loss (each a toggle
plus a percent input). Percent inputs are entered as whole percentages and divided by 100
on submit; invalid values set an `*Invalid` flag that shows an inline hint and disables
submit. The submit payload (a `BotSessionCreateRequest`) currently sends `take_profit_pct`
and `stop_loss_pct` but **not** `drawdown_stop_pct`.

The backend already supports a per-session drawdown threshold end-to-end:
`BotSessionCreateRequest.drawdown_stop_pct: float | None = Field(default=None, gt=0)`
(`api/schemas.py`), `create_bot_session(..., drawdown_stop_pct=...)` falling back to
`settings.BOT_DRAWDOWN_STOP_PCT` (0.25) when `None` (`strategy_bots/service.py`), the
non-null `BotSession.drawdown_stop_pct` column (`strategy_bots/models.py`), and the TS
type `BotSessionCreateRequest.drawdown_stop_pct?: number | null` (`types/api.ts`). The gap
is purely the form.

## Goals / Non-Goals

**Goals:**

- Let the user set the drawdown kill-switch threshold in the build form and send it on
  creation.
- Preserve today's behavior when the user leaves the field at its default (default = the
  configured default, 25%).
- Match the form's existing percent-field conventions (friendly percent units, ÷100 on
  submit, inline validation that blocks submit).

**Non-Goals:**

- No backend/API/schema/migration change; no change to the default `BOT_DRAWDOWN_STOP_PCT`.
- No change to take-profit/stop-loss, sizing, strategy params, the strategy catalog, or the
  strategy guide pages.
- The kill-switch is not made optional — it stays always-on.

## Decisions

### A required percent field, not a toggle

The drawdown kill-switch is always on (the model column is non-null), so unlike
take-profit / stop-loss it has **no enable/disable toggle**. The form adds a single
required percent input `drawdownStopPct` (string state, default `'25'`) and always includes
`drawdown_stop_pct` in the payload as `Number.parseFloat(drawdownStopPct) / 100`.

- **Alternative considered:** send `drawdown_stop_pct` only when the user changes it (let
  `null` fall back to the backend default). Rejected — sending the shown value is clearer
  and keeps the UI the single source of truth for what the user sees versus what is saved;
  defaulting the input to `25` already reproduces the backend default.

### Default value sourced as the literal `25`

The field defaults to `'25'`, mirroring the backend default `BOT_DRAWDOWN_STOP_PCT = 0.25`.
The configured default is a backend setting not currently exposed to the frontend, and this
change is explicitly frontend-only, so the form hard-codes the matching percent literal
(as the existing sizing fields already do for their defaults, e.g. ATR period `14`, risk
`1`). A hint line notes it defaults to the configured default.

- **Alternative considered:** fetch the backend default via an endpoint/catalog field.
  Rejected as out of scope (no backend change); the literal stays in sync with the one
  documented default and is covered by a test asserting the default renders.

### Validation: `0 < pct < 100`

Reuse the established pattern: compute `drawdownFraction = parseFloat(drawdownStopPct) / 100`
and `drawdownValid = Number.isFinite(drawdownFraction) && drawdownFraction > 0 &&
drawdownFraction < 1`. Add `drawdownValid` to the submit-enable guard and derive
`drawdownInvalid = drawdownStopPct.length > 0 && !drawdownValid` to show the inline invalid
hint. This matches the API's `gt=0` and the fraction semantics (a threshold of 100%+ is
meaningless for a peak-to-trough drawdown).

### Placement

Render the field in the exit/risk-control group alongside take-profit and stop-loss, with a
hint explaining the kill-switch liquidates all positions and stops the bot when total value
falls this far from its peak. Always visible (not gated on sizing method or a toggle).

## Risks / Trade-offs

- [Hard-coded `25` default could drift from `BOT_DRAWDOWN_STOP_PCT`] → Low risk; the default
  rarely changes and the existing form already hard-codes sizing defaults the same way. A
  test pins the rendered default; revisit with a config endpoint if defaults start to move.
- [Users may set an aggressive threshold (e.g. 1%)] → Acceptable; it is a deliberate user
  choice within the valid range, same as take-profit/stop-loss.

## Open Questions

_None._
