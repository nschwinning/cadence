## Context

Course Algo 3: `gradient = 2 × (price − mean(last 5 prices))`; `gradient < 0` → long, `> 0` → short,
`= 0` → flat; the position is re-decided every price; no TP/SL; 5% drawdown stop; its "step size"
only feeds the script's cash bookkeeping. Long-only: long while price < mean5, flat otherwise.
Rolling-Average Reversion in `band` mode enters on `deviation < −entry_threshold` and, in `revert`
mode, exits on `deviation ≥ −exit_threshold` — with both thresholds 0 that is exactly Algo 3. Its
params validator currently demands `exit_threshold < entry_threshold` (and `exit_z < entry_z`).

## Goals / Non-Goals

**Goals:** express Algo 3 as a preset by allowing equal thresholds; keep every existing behaviour.

**Non-Goals:** a separate strategy; the course's step-size bookkeeping (sizing is the engine's).

## Decisions

1. **Relax the validator to `exit ≤ entry`** for both band and z-score in revert mode. Equal levels
   cannot cause an enter-and-exit on the same bar (strict `<` vs `≥`), and the next bar re-evaluates
   — matching the course's per-price re-decision. Larger exit than entry stays rejected.
2. **Preset** `rolling_reversion_gradient_algo3`: `average_type='sma'`, `window=5`, `distance='band'`,
   `entry_threshold=0`, `exit_threshold=0`, `entry_z=1.0`, `exit_z=0.2`, `exit_mode='revert'`;
   TP None, SL None, DD 0.05; `course_ref='Algo 3'`, not the strategy default (Algo 5 stays default).
3. **Frontend**: the reversion order check becomes `exit ≤ entry`; the hint text changes from "Must
   be below the entry" to "At most the entry".

## Risks / Trade-offs

- Zero thresholds on 5-bar windows trade very often; course recipe, drawdown stop bounds it.

## Migration Plan

None. Existing sessions' params remain valid under the looser rule.

## Open Questions

None.
