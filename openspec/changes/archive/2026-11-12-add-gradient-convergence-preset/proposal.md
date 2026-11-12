## Why

The last course port in roadmap Tier 2 is **Gradient Convergence** (#12, course Algo 3). Read
long-only, its signal is: hold a long while the close is below its 5-bar mean (the course's
"gradient" 2 × (price − mean) is negative), be flat once it is back at or above it. That is exactly
the **Rolling-Average Reversion** bot with an SMA over 5 bars and zero entry / exit thresholds — the
roadmap's rule is to never build the same signal twice, so Algo 3 becomes a preset, not a new
strategy (user decision).

## What Changes

- **Rolling-Average Reversion**: in `revert` mode the exit level may now **equal** the entry level
  (`exit_threshold ≤ entry_threshold`, `exit_z ≤ entry_z`); previously it had to be strictly above.
  Still safe: entry needs the measure strictly below the entry level, the exit fires at or above,
  so a trade can't enter and exit on the same bar. Existing presets and sessions are unaffected.
- New preset **Gradient Convergence (Algo 3)** on Rolling-Average Reversion: SMA, window 5, band,
  entry 0, exit 0, revert exit; TP off, SL off (course has none), drawdown 5%.
- Build form accepts equal thresholds; roadmap: Gradient Convergence shipped as a preset (Tier 2
  course ports complete).
- No new strategy, no migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: relaxes the Rolling-Average Reversion threshold-order rule; adds the Gradient
  Convergence preset to the catalog.

## Impact

- Backend: `strategy_bots/rolling_average_reversion.py` (validator), `presets.py`.
- Frontend: `BuildBotCard.tsx` (reversion threshold-order check `<` → `≤`).
- Docs: `docs/trading-bots-roadmap.md`.
