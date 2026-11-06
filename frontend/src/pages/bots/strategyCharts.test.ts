import { describe, it, expect } from 'vitest';
import { getStrategyChart } from './strategyCharts';
import { crossoverSignals } from './crossoverChart';
import { rsiSignals, wilderRsiSeries } from './rsiChart';

describe('strategyCharts registry', () => {
  it('returns the MA-Crossover descriptor for ma_crossover', () => {
    const chart = getStrategyChart('ma_crossover');
    expect(chart).toBeDefined();
    expect(chart?.ariaLabel).toMatch(/crossover with entry and exit markers/i);
    const option = chart?.buildOption() as { series: { name: string }[] };
    expect(option.series.map((s) => s.name)).toEqual(['Fast SMA', 'Slow SMA']);
  });

  it('returns the RSI descriptor for rsi_mean_reversion', () => {
    const chart = getStrategyChart('rsi_mean_reversion');
    expect(chart).toBeDefined();
    expect(chart?.ariaLabel).toMatch(/rsi mean-reversion/i);
    const option = chart?.buildOption() as { series: { name: string }[] };
    expect(option.series.map((s) => s.name)).toEqual(['RSI']);
  });

  it('returns undefined for an unregistered strategy key', () => {
    expect(getStrategyChart('does_not_exist')).toBeUndefined();
  });
});

describe('rsiChart', () => {
  it('matches the backend Wilder RSI on known monotonic series', () => {
    expect(wilderRsiSeries([1, 2, 3, 4], 2).at(-1)).toBe(100);
    expect(wilderRsiSeries([4, 3, 2, 1], 2).at(-1)).toBe(0);
    expect(wilderRsiSeries([10, 11, 10, 11], 2).at(-1)).toBeCloseTo(75);
  });

  it('detects an oversold entry followed by a reversion exit', () => {
    const signals = rsiSignals();
    expect(signals.some((s) => s.kind === 'entry')).toBe(true);
    expect(signals.some((s) => s.kind === 'exit')).toBe(true);
    // Entry precedes the exit (long-only round trip).
    const entry = signals.find((s) => s.kind === 'entry')!;
    const exit = signals.find((s) => s.kind === 'exit')!;
    expect(entry.index).toBeLessThan(exit.index);
  });

  it('builds a single-line RSI option on a 0–100 axis with mark-lines', () => {
    const option = getStrategyChart('rsi_mean_reversion')!.buildOption() as {
      yAxis: { min: number; max: number };
      series: { name: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.yAxis.min).toBe(0);
    expect(option.yAxis.max).toBe(100);
    expect(option.series).toHaveLength(1);
    // Two level lines plus at least one entry/exit mark.
    expect(option.series[0].markLine?.data.length).toBeGreaterThanOrEqual(3);
  });
});

describe('crossoverChart', () => {
  it('detects one entry up-cross and one exit down-cross', () => {
    const signals = crossoverSignals();
    expect(signals.some((s) => s.kind === 'entry')).toBe(true);
    expect(signals.some((s) => s.kind === 'exit')).toBe(true);
  });

  it('builds a two-line option with entry/exit mark-lines', () => {
    const option = getStrategyChart('ma_crossover')!.buildOption() as {
      series: { name: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series).toHaveLength(2);
    expect(option.series.map((s) => s.name)).toEqual(['Fast SMA', 'Slow SMA']);
    const markLine = option.series[0].markLine;
    expect(markLine?.data.length).toBeGreaterThanOrEqual(2);
  });
});
