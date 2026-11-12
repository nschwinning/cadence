import type { EChartsCoreOption } from 'echarts/core';

interface SyntheticBar {
  open: number;
  high: number;
  low: number;
  close: number;
}

/**
 * A fixed, deterministic synthetic OHLC series: a drift lower, a run higher (the
 * Heikin-Ashi candles turn green → entry), then a pull-back (first red candle → exit).
 * Purely illustrative, not market data.
 */
const SYNTHETIC_BARS: SyntheticBar[] = [
  { open: 105, high: 105.5, low: 103.5, close: 104 },
  { open: 104, high: 104.5, low: 102.5, close: 103 },
  { open: 103, high: 103.5, low: 101.5, close: 102 },
  { open: 102, high: 102.5, low: 100.5, close: 101 },
  { open: 101, high: 103, low: 100.5, close: 102.5 },
  { open: 102.5, high: 105, low: 102, close: 104.5 },
  { open: 104.5, high: 107, low: 104, close: 106.5 },
  { open: 106.5, high: 109, low: 106, close: 108.5 },
  { open: 108.5, high: 110.5, low: 108, close: 110 },
  { open: 110, high: 111, low: 108, close: 108.5 },
  { open: 108.5, high: 109, low: 105.5, close: 106 },
  { open: 106, high: 106.5, low: 103.5, close: 104 },
];

/** One Heikin-Ashi candle. */
export interface HaCandle {
  open: number;
  high: number;
  low: number;
  close: number;
}

/** Heikin-Ashi candles for the synthetic bars — mirrors the backend helper. */
export function heikinAshiCandles(): HaCandle[] {
  const candles: HaCandle[] = [];
  SYNTHETIC_BARS.forEach((bar, i) => {
    const close = (bar.open + bar.high + bar.low + bar.close) / 4;
    const open =
      i === 0 ? (bar.open + bar.close) / 2 : (candles[i - 1].open + candles[i - 1].close) / 2;
    candles.push({
      open,
      close,
      high: Math.max(bar.high, open, close),
      low: Math.min(bar.low, open, close),
    });
  });
  return candles;
}

/** An entry/exit signal with the x-index it occurs at. */
export interface HaSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/** Entry on the first green candle while flat, exit on the next red one. */
export function heikinAshiSignals(): HaSignal[] {
  const signals: HaSignal[] = [];
  let holding = false;
  heikinAshiCandles().forEach((c, index) => {
    const green = c.close > c.open;
    if (!holding && green) {
      signals.push({ index, kind: 'entry' });
      holding = true;
    } else if (holding && !green) {
      signals.push({ index, kind: 'exit' });
      holding = false;
    }
  });
  return signals;
}

/**
 * Build the ECharts option for the illustrative Heikin-Ashi Trend chart: the
 * Heikin-Ashi candles (green up, red down) with vertical mark-lines at the entry and
 * exit. Deterministic and self-contained.
 */
export function buildHeikinAshiChartOption(): EChartsCoreOption {
  const candles = heikinAshiCandles();
  const marks = heikinAshiSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['Heikin-Ashi'], top: 0 },
    xAxis: { type: 'category', data: candles.map((_, i) => String(i)) },
    yAxis: { type: 'value', scale: true },
    series: [
      {
        id: 'heikin-ashi',
        name: 'Heikin-Ashi',
        type: 'candlestick',
        // ECharts candlestick data order: [open, close, low, high].
        data: candles.map((c) => [c.open, c.close, c.low, c.high]),
        itemStyle: {
          color: '#059669',
          color0: '#dc2626',
          borderColor: '#059669',
          borderColor0: '#dc2626',
        },
        markLine: { symbol: 'none', data: marks },
      },
    ],
  };
}
