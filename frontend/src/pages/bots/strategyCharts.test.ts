import { describe, it, expect } from 'vitest';
import { getStrategyChart } from './strategyCharts';
import { crossoverSignals } from './crossoverChart';

describe('strategyCharts registry', () => {
  it('returns the MA-Crossover descriptor for ma_crossover', () => {
    const chart = getStrategyChart('ma_crossover');
    expect(chart).toBeDefined();
    expect(chart?.ariaLabel).toMatch(/crossover with entry and exit markers/i);
    const option = chart?.buildOption() as { series: { name: string }[] };
    expect(option.series.map((s) => s.name)).toEqual(['Fast SMA', 'Slow SMA']);
  });

  it('returns undefined for an unregistered strategy key', () => {
    expect(getStrategyChart('does_not_exist')).toBeUndefined();
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
