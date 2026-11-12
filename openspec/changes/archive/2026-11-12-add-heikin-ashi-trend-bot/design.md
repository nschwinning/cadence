## Context

Course Algo 11 aggregates ticks into candles, converts each into a Heikin-Ashi candle (close =
OHLC mean; open = (o + c) / 2 for the first, then the mean of the previous HA open and close), and
trades the colour: green → long, red → exit; TP 0.5%, SL 1%, drawdown 5% (its ATR is only logged).
Course Algo 37 adds volume: enter on green **and** tick volume > the average of the last 20 tick
volumes; exit on red **or** volume ≤ average; no TP/SL; drawdown 5%. Cadence bars carry real OHLCV.

## Goals / Non-Goals

**Goals:** a faithful long-only port of both as one strategy with an optional volume filter; two
presets; form; guide; roadmap.

**Non-Goals:** the course ATR (logged only); short legs; tick-level volume (bars only).

## Decisions

1. **One strategy, `volume_filter` toggle** — the roadmap groups 11 and 37 as one bot ("37 = 11 +
   volume-confirmation toggle"). `HeikinAshiTrendParams`: `volume_filter` (False), `volume_window`
   ≥ 2 (20).
2. **Heikin-Ashi replay**: the HA open halves the influence of older candles each bar, so the
   strategy replays a fixed span — `required_history` = 10 (the course warm-up) without the filter,
   `max(10, volume_window)` with it. After 10 candles the seed's influence on the open is < 0.1%.
3. **Volume**: strong ⇔ latest bar volume > mean volume of the latest `volume_window` bars (current
   bar included, like the course's deque). Zero mean → not strong. The course compares the last
   *tick* volume with a 20-*tick* average; the port uses bars — recorded as the adaptation.
4. **Presets** `heikin_ashi_algo11` (default; filter off; TP 0.005, SL 0.01, DD 0.05) and
   `heikin_ashi_volume_algo37` (filter on, window 20; TP None, SL None, DD 0.05).
5. **Frontend**: `BuildBotCard` Heikin-Ashi branch: "Require above-average volume" checkbox
   revealing "Volume window (bars)"; `volume_window` is sent only when the filter is on so the
   Algo 11 preset compares equal. `heikinAshiChart.ts` draws HA candles (candlestick series) over a
   synthetic OHLC series with entry / exit markers.

## Risks / Trade-offs

- Heikin-Ashi flips colour often on choppy 5-minute bars; the Algo 11 brackets bound each trade.
- Bar volume on the IEX feed is partial (roadmap Tier 3 caveat); the filter compares the bar with
  its own recent average, so the partial feed cancels out to first order.

## Migration Plan

None (additive).

## Open Questions

None.
