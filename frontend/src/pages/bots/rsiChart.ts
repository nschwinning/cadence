import type { EChartsCoreOption } from 'echarts/core';

/** RSI window used by the illustrative chart (not the live default of 14). */
const RSI_PERIOD = 5;
/** Oversold / exit levels drawn as reference bands (illustrative, not the live defaults). */
const OVERSOLD = 30;
const EXIT_LEVEL = 50;

/**
 * A fixed, deterministic synthetic price series shaped to drive RSI down into the
 * oversold band (entry) and then back up through the exit level (exit) — purely
 * illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  110, 108, 107, 105, 102, 100, 98, 96, 95, 94, 95, 97, 100, 103, 105, 106,
  107, 108, 109, 110,
] as const;

/**
 * Latest-aligned Wilder RSI series over `values`: the first `period` points are
 * null (warm-up), then each point is the Wilder-smoothed RSI through that bar.
 * Mirrors the backend's `_wilder_rsi` so the illustration matches the strategy.
 */
export function wilderRsiSeries(
  values: readonly number[],
  period: number,
): (number | null)[] {
  const out: (number | null)[] = values.map(() => null);
  if (values.length <= period) return out;

  const deltas = values.slice(1).map((v, i) => v - values[i]);
  const gains = deltas.map((d) => Math.max(d, 0));
  const losses = deltas.map((d) => Math.max(-d, 0));

  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;

  const rsiAt = (gain: number, loss: number) =>
    loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);

  // deltas[i] is the return into values[i + 1]; the seeded window ends at
  // values[period], so that is the first bar with a defined RSI.
  out[period] = rsiAt(avgGain, avgLoss);
  for (let i = period; i < deltas.length; i += 1) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    out[i + 1] = rsiAt(avgGain, avgLoss);
  }
  return out;
}

/** An entry/exit signal with the x-index it occurs at. */
export interface RsiSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/**
 * Detect the illustrative long-only RSI mean-reversion signals from the synthetic
 * series: an **entry** on the first bar RSI dips below the oversold level while
 * flat, an **exit** on the first bar RSI reverts above the exit level while long.
 * Deterministic for the fixed synthetic series.
 */
export function rsiSignals(): RsiSignal[] {
  const rsi = wilderRsiSeries(SYNTHETIC_PRICES, RSI_PERIOD);
  const signals: RsiSignal[] = [];
  let holding = false;
  for (let i = 0; i < rsi.length; i += 1) {
    const value = rsi[i];
    if (value == null) continue;
    if (!holding && value < OVERSOLD) {
      signals.push({ index: i, kind: 'entry' });
      holding = true;
    } else if (holding && value > EXIT_LEVEL) {
      signals.push({ index: i, kind: 'exit' });
      holding = false;
    }
  }
  return signals;
}

/**
 * Build the ECharts option for the illustrative RSI mean-reversion chart: the RSI
 * line over a synthetic price series on a fixed 0–100 axis, with horizontal
 * reference lines at the oversold and exit levels and vertical mark-lines at the
 * entry (green, oversold dip) and exit (red, reversion) points. Fully
 * deterministic and self-contained — it takes no live data.
 */
export function buildRsiChartOption(): EChartsCoreOption {
  const rsi = wilderRsiSeries(SYNTHETIC_PRICES, RSI_PERIOD);
  const x = SYNTHETIC_PRICES.map((_, i) => String(i));
  const signals = rsiSignals();

  const verticalMarks = signals.map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));

  const levelMarks = [
    {
      yAxis: OVERSOLD,
      lineStyle: { color: '#94a3b8', type: 'dashed' as const },
      label: { formatter: `Oversold ${OVERSOLD}`, color: '#64748b' },
    },
    {
      yAxis: EXIT_LEVEL,
      lineStyle: { color: '#94a3b8', type: 'dashed' as const },
      label: { formatter: `Exit ${EXIT_LEVEL}`, color: '#64748b' },
    },
  ];

  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['RSI'], top: 0 },
    xAxis: { type: 'category', data: x, boundaryGap: false },
    yAxis: { type: 'value', min: 0, max: 100 },
    series: [
      {
        id: 'rsi',
        name: 'RSI',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: '#8b5cf6' },
        data: rsi,
        markLine: {
          symbol: 'none',
          data: [...levelMarks, ...verticalMarks],
        },
      },
    ],
  };
}
