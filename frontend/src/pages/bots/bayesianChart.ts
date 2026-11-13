import type { EChartsCoreOption } from 'echarts/core';

/** Illustrative parameters: the course's regimes with a short evidence window. */
const DRIFT = 0.001;
const TREND_SIGMA = 0.002;
const FLAT_SIGMA = 0.0008;
const THRESHOLD = 0.6;
const REPLAY_BARS = 8;

type State = 'UP' | 'FLAT' | 'DOWN';
const STATES: State[] = ['UP', 'FLAT', 'DOWN'];

/** Per-bar fractional moves: sideways, a climb, sideways, a slide. */
const MOVES = [
  0.0003, -0.0004, 0.0002, -0.0002, 0.0004, -0.0003, 0.0001, -0.0001, 0.0002, -0.0002,
  0.0025, 0.0018, 0.003, 0.002, 0.0028, 0.0015, 0.0022, 0.0026, 0.0003, -0.0004, 0.0002,
  -0.0003, 0.0004, -0.0002, -0.0026, -0.002, -0.003, -0.0018, -0.0024, -0.0022, -0.0028,
] as const;

/**
 * A fixed, deterministic synthetic close series built from `MOVES`. Purely illustrative,
 * not market data.
 */
const SYNTHETIC_PRICES: number[] = MOVES.reduce<number[]>(
  (closes, move) => [...closes, closes[closes.length - 1] * (1 + move)],
  [100],
);

function logPdf(x: number, mean: number, sigma: number): number {
  return -Math.log(sigma * Math.sqrt(2 * Math.PI)) - 0.5 * ((x - mean) / sigma) ** 2;
}

const PARAMS: Record<State, [number, number]> = {
  UP: [DRIFT, TREND_SIGMA],
  FLAT: [0, FLAT_SIGMA],
  DOWN: [-DRIFT, TREND_SIGMA],
};

/** Regime probabilities at bar `i`, replayed from equal priors (mirrors the backend). */
function posteriorAt(i: number): Record<State, number> {
  const logPost: Record<State, number> = {
    UP: Math.log(1 / 3),
    FLAT: Math.log(1 / 3),
    DOWN: Math.log(1 / 3),
  };
  for (let j = i - REPLAY_BARS + 1; j <= i; j += 1) {
    const delta = (SYNTHETIC_PRICES[j] - SYNTHETIC_PRICES[j - 1]) / SYNTHETIC_PRICES[j - 1];
    for (const state of STATES) logPost[state] += logPdf(delta, ...PARAMS[state]);
    const peak = Math.max(...STATES.map((s) => logPost[s]));
    const total = peak + Math.log(STATES.reduce((a, s) => a + Math.exp(logPost[s] - peak), 0));
    for (const state of STATES) logPost[state] -= total;
  }
  return { UP: Math.exp(logPost.UP), FLAT: Math.exp(logPost.FLAT), DOWN: Math.exp(logPost.DOWN) };
}

/** Per bar: the regime probabilities, or null before a full evidence window. */
export function regimeProbabilities(): (Record<State, number> | null)[] {
  return SYNTHETIC_PRICES.map((_, i) => (i < REPLAY_BARS ? null : posteriorAt(i)));
}

/** An entry/exit signal with the x-index it occurs at. */
export interface BayesSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/** Entry on a confident up-regime; exit on a confident down-regime. */
export function bayesSignals(): BayesSignal[] {
  const signals: BayesSignal[] = [];
  let holding = false;
  regimeProbabilities().forEach((p, index) => {
    if (p === null) return;
    const best = STATES.reduce((a, b) => (p[b] > p[a] ? b : a));
    const confident = p[best] >= THRESHOLD;
    if (!holding && best === 'UP' && confident) {
      signals.push({ index, kind: 'entry' });
      holding = true;
    } else if (holding && best === 'DOWN' && confident) {
      signals.push({ index, kind: 'exit' });
      holding = false;
    }
  });
  return signals;
}

/**
 * Build the ECharts option for the illustrative Bayesian Trend Predictor chart: the
 * synthetic close on top, the three regime probabilities as stacked areas below (0–1)
 * with the confidence threshold dashed, and vertical mark-lines at the entry and exit.
 * Deterministic and self-contained.
 */
export function buildBayesianChartOption(): EChartsCoreOption {
  const probabilities = regimeProbabilities();
  const marks = bayesSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  const categories = SYNTHETIC_PRICES.map((_, i) => String(i));
  const area = (state: State, name: string, color: string) => ({
    id: state.toLowerCase(),
    name,
    type: 'line',
    xAxisIndex: 1,
    yAxisIndex: 1,
    stack: 'regime',
    showSymbol: false,
    lineStyle: { width: 0 },
    areaStyle: { color },
    itemStyle: { color },
    data: probabilities.map((p) => (p === null ? null : p[state])),
  });
  return {
    grid: [
      { left: 48, right: 24, top: 32, height: '42%' },
      { left: 48, right: 24, top: '62%', bottom: 28 },
    ],
    legend: { data: ['Price', 'P(up)', 'P(flat)', 'P(down)'], top: 0 },
    xAxis: [
      { type: 'category', data: categories, boundaryGap: false, gridIndex: 0 },
      { type: 'category', data: categories, boundaryGap: false, gridIndex: 1 },
    ],
    yAxis: [
      { type: 'value', scale: true, gridIndex: 0 },
      { type: 'value', min: 0, max: 1, gridIndex: 1 },
    ],
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
      area('UP', 'P(up)', '#86efac'),
      area('FLAT', 'P(flat)', '#cbd5e1'),
      {
        ...area('DOWN', 'P(down)', '#fca5a5'),
        markLine: {
          symbol: 'none',
          data: [{ yAxis: THRESHOLD, label: { formatter: 'Confidence' } }],
          lineStyle: { type: 'dashed', color: '#64748b' },
        },
      },
    ],
  };
}
