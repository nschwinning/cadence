## Why

The last Tier 2 bot on the roadmap (`docs/trading-bots-roadmap.md`, #13) is **Trend Confirmation**:
not a course port but an intraday bot derived from the AI portfolio's technical trend gate. Its
identity is a strict **AND** of a few trend legs — distinct from single-indicator bots (MA
Crossover, MACD) and from the later Multi-Signal Consensus (a vote). The roadmap rejected a literal
daily port (SMA200 on 5-minute bars is ~2.5 days) in favour of re-tuned intraday legs (option B).

## What Changes

- New strategy **Trend Confirmation** (`trend_confirmation`), pure and long-only. Legs:
  SMA fast > SMA slow (trend), MACD histogram > 0 (momentum), RSI between an entry level and a cap
  (strong, not exhausted), and optional ROC > 0 and OBV-rising legs. **Enter** when all active legs
  agree; **exit** when any breaks — with an RSI exit level below the entry level (hysteresis) and no
  exit for being above the cap, so 5-minute noise doesn't churn positions.
- Defaults (user-approved): SMA 20 / 50, MACD 12 / 26 / 9, RSI 14 entering between 50 and 70 and
  exiting below 45, ROC 12 and OBV 20 legs off.
- Preset **Trend Confirmation (Cadence)** — default: the values above, TP 1%, SL 1%, drawdown 5%
  (Cadence's own recipe; no course values exist).
- **Shared indicator maths**: the SMA / MACD / Wilder RSI / ROC / OBV series functions move out of
  the AI gate's `compute_snapshot` into a shared module used by both; the gate's outputs are
  unchanged (parity test).
- Build form inputs, a strategy-guide illustration, roadmap update. No migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the Trend Confirmation strategy and its preset.

## Impact

- Backend: new `technical_indicators/series.py` (shared pandas series functions);
  `technical_indicators/compute.py` uses them (no behaviour change); new
  `strategy_bots/trend_confirmation.py`; `constants.py`, `registry.py`, `presets.py`.
- Frontend: `BuildBotCard.tsx` (trend-confirmation fields), new `trendConfirmationChart.ts` in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md` (Tier 2 complete).
- Out of scope: per-bot timeframes (daily bars for bots) — a separate engine capability.
