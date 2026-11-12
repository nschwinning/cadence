## Context

Course Algo 18 keeps the latest 20 prices, computes `mean` of the last 5, 10 and 20, enters long on
`fast > mid > slow`, and exits only by TP 0.5% / SL 1%; drawdown 5%.

## Goals / Non-Goals

**Goals:** a faithful long-only port, preset, form, guide, roadmap.

**Non-Goals:** a ribbon-break exit (the course has none); the short leg.

## Decisions

1. **Stateless**: SMAs of the latest closes (current bar included); `required_history` =
   `slow_period`. No replay needed.
2. **`MaRibbonParams`**: `fast_period` ≥ 1 (5), `mid_period` (10), `slow_period` (20), validated
   strictly increasing.
3. **Signals**: flat → ENTER_LONG iff fast > mid > slow; holding → HOLD (engine exits).
4. **Preset** `ma_ribbon_algo18` (default): 5/10/20; TP 0.005, SL 0.01, DD 0.05.
5. **Frontend**: `BuildBotCard` ribbon branch (Fast, Mid, Slow SMA; strictly increasing) with its own
   setters (`fast_period` / `slow_period` are also MA Crossover names; `mid_period` is new).
   `maRibbonChart.ts` plots a synthetic close with the three SMAs and the entry marker.

## Risks / Trade-offs

- Holding until TP/SL means a position is kept even after the ribbon unwinds — course behaviour;
  the 1% stop bounds it.

## Migration Plan

None (additive).

## Open Questions

None.
