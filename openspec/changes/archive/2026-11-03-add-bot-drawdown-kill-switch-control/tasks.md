## 1. Drawdown kill-switch field in the build form

- [x] 1.1 In `frontend/src/pages/bots/BuildBotCard.tsx` add a required drawdown kill-switch
  percent control: a `drawdownStopPct` string state defaulting to `'25'`, rendered as a
  `NumberField` "Drawdown kill-switch (%)" in the exit/risk-control group near take-profit /
  stop-loss, with a hint that it liquidates all positions and stops the bot when total value
  falls this far from its peak (and that it defaults to the configured default). It is always
  shown — no enable/disable toggle.
- [x] 1.2 Add validation matching the form's pattern: `drawdownFraction = parseFloat(drawdownStopPct) / 100`,
  `drawdownValid = Number.isFinite(drawdownFraction) && drawdownFraction > 0 && drawdownFraction < 1`;
  include `drawdownValid` in the submit-enable guard and derive `drawdownInvalid` to show the
  inline invalid hint when the entry is non-empty and out of range.
- [x] 1.3 Include `drawdown_stop_pct: drawdownFraction` in the `BotSessionCreateRequest`
  submit payload (always sent).

## 2. Tests

- [x] 2.1 Verify a Vitest test in the BuildBotCard test file that the form renders a drawdown
  kill-switch field defaulting to `25`, and that a valid submission includes
  `drawdown_stop_pct` equal to the entered percent ÷ 100 (e.g. entering `5` → `0.05`).
- [x] 2.2 Verify a Vitest test that an out-of-range drawdown value (e.g. `0` or `150`) shows
  the inline invalid hint and blocks submission (submit button disabled / create not called).

## 3. Verification gates

- [x] 3.1 Frontend green: `cd frontend && npm run typecheck && npm run test && npm run build`.
- [x] 3.2 Spec/change valid: `openspec validate add-bot-drawdown-kill-switch-control --strict`.
