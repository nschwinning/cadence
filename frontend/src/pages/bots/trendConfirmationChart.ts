import type { EChartsCoreOption } from 'echarts/core';

/** Short windows used by the illustrative chart (not the live 5-minute defaults). */
const SMA_FAST = 5;
const SMA_SLOW = 12;
const MACD_FAST = 4;
const MACD_SLOW = 9;
const MACD_SIGNAL = 3;
const RSI_PERIOD = 6;
const RSI_ENTRY = 50;
const RSI_MAX = 80;
const RSI_EXIT = 45;

/**
 * A fixed, deterministic synthetic close series: a gentle slide, an accelerating uptrend
 * with small pull-backs (every leg agrees → entry), then a roll-over (a leg breaks →
 * exit).
 * Purely illustrative, not market data.
 */
const SYNTHETIC_PRICES: number[] = [
  100, 99.85, 99.7, 99.55, 99.4, 99.25, 99.1, 98.95, 98.8, 98.65, 98.5, 98.35, 98.2, 98.05,
  97.9, 97.75, 98.2, 98.82, 98.62, 99.28, 99.96, 99.76, 100.48, 101.22, 101.02, 101.8, 102.6,
  102.4, 103.24, 104.1, 103.9, 104.8, 105.72, 105.52, 106.48, 107.46, 106.56, 105.66, 104.76,
  103.86, 102.96, 102.06, 101.16, 100.26, 99.36, 98.46, 97.56, 96.66,
];

type Series = (number | null)[];

/** Simple moving average (null until `n` values). */
export function sma(values: number[], n: number): Series {
  return values.map((_, i) =>
    i + 1 < n ? null : values.slice(i + 1 - n, i + 1).reduce((a, b) => a + b, 0) / n,
  );
}

/** pandas `ewm(span, adjust=False, min_periods=span)` over the non-null values. */
function ema(values: Series, span: number): Series {
  const alpha = 2 / (span + 1);
  let prev: number | null = null;
  let count = 0;
  return values.map((v) => {
    if (v == null) return null;
    prev = prev == null ? v : alpha * v + (1 - alpha) * prev;
    count += 1;
    return count >= span ? prev : null;
  });
}

/** MACD histogram (line − signal), mirroring the shared backend series. */
export function macdHistogram(values: number[]): Series {
  const fast = ema(values, MACD_FAST);
  const slow = ema(values, MACD_SLOW);
  const line = values.map((_, i) =>
    fast[i] == null || slow[i] == null ? null : fast[i]! - slow[i]!,
  );
  const signal = ema(line, MACD_SIGNAL);
  return line.map((l, i) => (l == null || signal[i] == null ? null : l - signal[i]!));
}

/** Wilder-smoothed RSI, mirroring the shared backend series. */
export function rsi(values: number[], n: number): Series {
  const out: Series = values.map(() => null);
  let avgGain: number | null = null;
  let avgLoss: number | null = null;
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < values.length; i += 1) {
    const delta = values[i] - values[i - 1];
    const gain = Math.max(delta, 0);
    const loss = Math.max(-delta, 0);
    if (avgGain == null || avgLoss == null) {
      gains.push(gain);
      losses.push(loss);
      if (gains.length === n) {
        avgGain = gains.reduce((a, b) => a + b, 0) / n;
        avgLoss = losses.reduce((a, b) => a + b, 0) / n;
      } else {
        continue;
      }
    } else {
      avgGain = (avgGain * (n - 1) + gain) / n;
      avgLoss = (avgLoss * (n - 1) + loss) / n;
    }
    if (avgGain === 0 && avgLoss === 0) out[i] = null;
    else if (avgLoss === 0) out[i] = 100;
    else out[i] = 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

/** An entry/exit signal with the x-index it occurs at. */
export interface TrendSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/** Entry when every leg agrees; exit when any leg breaks (RSI exit below RSI_EXIT). */
export function trendConfirmationSignals(): TrendSignal[] {
  const fast = sma(SYNTHETIC_PRICES, SMA_FAST);
  const slow = sma(SYNTHETIC_PRICES, SMA_SLOW);
  const hist = macdHistogram(SYNTHETIC_PRICES);
  const strength = rsi(SYNTHETIC_PRICES, RSI_PERIOD);
  const signals: TrendSignal[] = [];
  let holding = false;
  SYNTHETIC_PRICES.forEach((_, i) => {
    const [f, s, h, r] = [fast[i], slow[i], hist[i], strength[i]];
    if (f == null || s == null || h == null || r == null) return;
    if (!holding && f > s && h > 0 && r > RSI_ENTRY && r < RSI_MAX) {
      signals.push({ index: i, kind: 'entry' });
      holding = true;
    } else if (holding && (f < s || h < 0 || r < RSI_EXIT)) {
      signals.push({ index: i, kind: 'exit' });
      holding = false;
    }
  });
  return signals;
}

/**
 * Build the ECharts option for the illustrative Trend Confirmation chart: the
 * synthetic close with the fast and slow SMAs, and vertical mark-lines where every leg
 * first agrees (entry) and where one breaks (exit). Deterministic and self-contained.
 */
export function buildTrendConfirmationChartOption(): EChartsCoreOption {
  const marks = trendConfirmationSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'All agree' : 'Leg breaks',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['Price', 'Fast SMA', 'Slow SMA'], top: 0 },
    xAxis: { type: 'category', data: SYNTHETIC_PRICES.map((_, i) => String(i)), boundaryGap: false },
    yAxis: { type: 'value', scale: true },
    series: [
      {
        id: 'price',
        name: 'Price',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: '#2563eb' },
        data: SYNTHETIC_PRICES.slice(),
        markLine: { symbol: 'none', data: marks },
      },
      {
        id: 'sma-fast',
        name: 'Fast SMA',
        type: 'line',
        showSymbol: false,
        itemStyle: { color: '#059669' },
        data: sma(SYNTHETIC_PRICES, SMA_FAST),
      },
      {
        id: 'sma-slow',
        name: 'Slow SMA',
        type: 'line',
        showSymbol: false,
        lineStyle: { type: 'dashed' },
        itemStyle: { color: '#dc2626' },
        data: sma(SYNTHETIC_PRICES, SMA_SLOW),
      },
    ],
  };
}
