## Context

Course Algo 48: `velocity = p[-1] − p[-2]`, `prev_velocity = p[-2] − p[-3]`,
`acceleration = velocity − prev_velocity`; long when `velocity < −2.0` and `acceleration > 0`; exit on
`velocity > 0` ("velocity flip"), TP 0.5%, SL 1%; drawdown 5%. `VELOCITY_WINDOW` (3) only sizes the
warm-up buffer.

## Goals / Non-Goals

**Goals:** a long-only port with a price-independent threshold (user decision); preset; form; guide;
roadmap.

**Non-Goals:** absolute-price thresholds; the short leg.

## Decisions

1. **Percent velocity**: velocity = (c₋₁ − c₋₂) / c₋₂, previous = (c₋₂ − c₋₃) / c₋₃, acceleration =
   their difference. `PriceVelocityReversalParams.threshold_pct` in (0, 1), default 0.002 (course ₹2 /
   ₹1,000). `required_history` = 3 (three closes; stateless).
2. **Signals**: flat → ENTER_LONG iff velocity < −threshold and acceleration > 0; holding → EXIT iff
   velocity > 0, else HOLD.
3. **Preset** `price_velocity_algo48` (default): 0.002; TP 0.005, SL 0.01, DD 0.05.
4. **Frontend**: branch with "Velocity threshold (% per bar)" entered in percent (0.2) and sent as a
   fraction (0.002), like the reversion band thresholds. `velocityChart.ts` plots a synthetic close
   with a sharp, decelerating drop (entry) and the first up-bar (exit).

## Risks / Trade-offs

- One-bar velocity is noisy on 5-minute bars; the TP/SL bracket bounds each trade (course recipe).

## Migration Plan

None (additive).

## Open Questions

None.
