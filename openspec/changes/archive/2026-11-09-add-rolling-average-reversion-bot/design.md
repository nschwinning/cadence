## Context

The porting contract is unchanged: a strategy is a pure, stateless signal over one
symbol's bars, long-only, with TP/SL/drawdown and sizing owned by the engine (see
`strategy.py`, and `donchian_breakout.py` for the closest precedent of one strategy with
a mode selector). Presets now live in `strategy_bots/presets.py` and drive the build
form, which currently selects presets only via the strategy dropdown and the Donchian
version selector.

Facts from the course scripts that shape the port:
- Algos 5, 4, 14 and 39 all append the current price to the window **before** computing
  the average, so the window includes the current bar (unlike Donchian, which excludes it).
- Algo 4 uses `np.std`, i.e. the **population** standard deviation.
- Algo 14's "VWAP" is an equal-weight rolling mean of price (identical to `sma`). Only
  Algo 39 is a true volume-weighted average.
- Algos 14 and 39 enter on a bare cross (`price < average`) and exit only through fixed
  TP/SL. Algos 5 and 4 exit on reversion, plus a 2% stop.

## Goals / Non-Goals

**Goals:**
- One strategy whose parameters reproduce Algos 5, 4, 14 and 39 exactly, as presets.
- A general preset selector in the form so a strategy can carry many presets.

**Non-Goals:**
- ADX or volume filters (Algo 15, Algo 35).
- Changing how any existing strategy or preset behaves.

## Decisions

**1. One params model with flat, mode-gated fields** (`RollingAverageReversionParams`,
`extra='forbid'`): `average_type`, `window`, `distance`, `entry_threshold`,
`exit_threshold`, `entry_z`, `exit_z`, `exit_mode`. Off-mode fields keep their defaults,
mirroring `DonchianBreakoutParams`. A discriminated union was rejected: it would change the
JSON params shape and the form's payload pattern for no practical gain.

**2. Long-only revert exit uses a one-sided test.** Algo 5 exits when
`abs(deviation) <= exit`. Without its short leg, a long whose close jumps from −2% to +1%
would *not* exit under that test (|+1%| > 0.5%). The port exits when
`deviation >= −exit_threshold` (and `z >= −exit_z`), so reverting **or overshooting** the
average exits. This is the faithful intent for a long-only port and is recorded in the
spec. In-band behaviour matches the course exactly.

**3. Validation.** `window ≥ 2`; thresholds `≥ 0` (band thresholds `< 1`). In `revert` mode
the exit level must be strictly above the entry level (`exit_threshold < entry_threshold`,
`exit_z < entry_z`), otherwise an entry could exit on the very next bar. A bare cross
(`entry_threshold = 0`) is therefore only valid with `bracket` exit — exactly the
Algo 14/39 shape. `bracket` mode skips the ordering check.

**4. Indicator math.** All computed over `bars[-window:]` (current bar included):
- `sma`: mean of closes. `typical`: mean of `(h + l + c) / 3`. `vwap`: `Σ(c·v) / Σv`, and
  HOLD when `Σv == 0`.
- The z-score uses the population std of the same price series as the average (closes for
  `sma`/`vwap`, typical prices for `typical`), and HOLDs when std is 0.
- `band` deviation divides by the average (always positive for real prices).
Pure helpers; no numpy, matching the existing strategies.

**5. Presets carry the full parameter dict** for every Rolling-Average Reversion preset
(all eight fields), and the form always submits all eight. This keeps the frontend's
key-by-key "customized" comparison exact without special-casing hidden fields. The backend
comparison already normalises through the schema. Keys:
`rolling_reversion_sma_band_algo5` (default), `rolling_reversion_zscore_algo4`,
`rolling_reversion_mean_cross_algo14`, `rolling_reversion_vwap_cross_algo39`.

**6. General preset selector in the form.** Shown under the strategy dropdown when the
selected strategy has more than one preset. Its value is the applied preset key, and
choosing an option calls `applyPreset`. It replaces the plain "Preset: …" text line for
multi-preset strategies; the Customized marker and Reset button stay. Donchian now has two
presets, so it gets the selector too. Its Version dropdown remains, and `applyPreset`
already sets `donchianVersion` from the preset's `version`, so the two stay in sync.
Rejected: removing the Donchian version selector (manual users still want to switch
version independently of presets).

**7. Form fields.** Average type (select), Window, Distance (select), then either
entry/exit **percent** inputs (band; sent as fractions, like TP/SL) or entry/exit **σ**
inputs (zscore), and Exit mode (select: "Revert to average" / "Hold — exit via TP/SL").
The params payload always sends all eight fields (Decision 5). Preset-to-form mapping
converts band fractions to percent strings, which needs a strategy-aware branch in the
param mapper because `entry_threshold`/`exit_threshold` are displayed as percents.

**8. Illustrative chart** `rollingReversionChart.ts`: a synthetic price series with its
rolling mean and a lower band, an entry marker where the close drops below the band, and
an exit marker where it reverts to the mean. Same structure as `rsiChart.ts`.

## Risks / Trade-offs

- [Course "ticks" become 5-minute bars, so a 60-bar window is ~5 trading hours rather than
  60 simulated ticks] → the same trade-off was accepted for every previous port; windows
  stay course-literal so the presets are recognisable, and users can retune.
- [The bracket presets enter on any close below the mean, so they trade frequently] →
  that is the course behaviour; the engine's max-positions, per-name cap and drawdown
  kill-switch still bound exposure.
- [Percent display of band thresholds risks float drift in the "customized" check] → the
  existing tolerance comparison (1e-9) already covers percent↔fraction conversion.
- [The form grows another strategy branch] → contained in one conditional block, matching
  the RSI and Donchian branches.

## Migration Plan

None. The strategy key is free text and presets are code-defined.
