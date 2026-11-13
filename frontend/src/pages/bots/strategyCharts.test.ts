import { describe, it, expect } from 'vitest';
import { getStrategyChart } from './strategyCharts';
import { crossoverSignals } from './crossoverChart';
import { adxSeries, adxSignals } from './adxChart';
import { atrBandSignals } from './atrBandChart';
import { donchianSignals } from './donchianChart';
import { heikinAshiCandles, heikinAshiSignals } from './heikinAshiChart';
import { hma, hmaSignals } from './hmaChart';
import { macdEntryIndex, macdPoints } from './macdChart';
import { ribbonEntryIndex, smaSeries } from './maRibbonChart';
import { smoothingFactors, vamaSignals } from './vamaChart';
import { velocitySignals } from './velocityChart';
import { regimeSignals } from './volatilityRegimeChart';
import { consensusEntries, consensusScores } from './consensusChart';
import { bayesSignals, regimeProbabilities } from './bayesianChart';
import { volumeSignals } from './volumeBreakoutChart';
import { rsi, sma, trendConfirmationSignals } from './trendConfirmationChart';
import { reversionSignals, rollingMean } from './rollingReversionChart';
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

  it('returns the Donchian descriptor for donchian_breakout', () => {
    const chart = getStrategyChart('donchian_breakout');
    expect(chart).toBeDefined();
    expect(chart?.ariaLabel).toMatch(/donchian range breakout/i);
    const option = chart?.buildOption() as { series: { name: string }[] };
    expect(option.series.map((s) => s.name)).toEqual([
      'Price',
      'Entry channel',
      'Exit channel',
    ]);
  });

  it('returns the reversion descriptor for rolling_average_reversion', () => {
    const chart = getStrategyChart('rolling_average_reversion');
    expect(chart).toBeDefined();
    expect(chart?.ariaLabel).toMatch(/rolling-average reversion/i);
    const option = chart?.buildOption() as { series: { name: string }[] };
    expect(option.series.map((s) => s.name)).toEqual([
      'Price',
      'Rolling average',
      'Entry band',
    ]);
  });

  it('returns undefined for an unregistered strategy key', () => {
    expect(getStrategyChart('does_not_exist')).toBeUndefined();
  });
});

describe('donchianChart', () => {
  it('detects an upward-breakout entry followed by a downward-breakdown exit', () => {
    const signals = donchianSignals();
    expect(signals.some((s) => s.kind === 'entry')).toBe(true);
    expect(signals.some((s) => s.kind === 'exit')).toBe(true);
    // Entry precedes the exit (long-only round trip).
    const entry = signals.find((s) => s.kind === 'entry')!;
    const exit = signals.find((s) => s.kind === 'exit')!;
    expect(entry.index).toBeLessThan(exit.index);
  });

  it('builds a price + two channel lines with entry/exit mark-lines', () => {
    const option = getStrategyChart('donchian_breakout')!.buildOption() as {
      series: { name: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series).toHaveLength(3);
    const markLine = option.series[0].markLine;
    expect(markLine?.data.length).toBeGreaterThanOrEqual(2);
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

describe('rollingReversionChart', () => {
  it('computes a window mean including the current bar', () => {
    expect(rollingMean([1, 2, 3, 4, 5, 6], 3)).toBeNull();
    expect(rollingMean([1, 2, 3, 4, 5, 6], 5)).toBe(4);
  });

  it('detects a dip entry followed by a reversion exit', () => {
    const signals = reversionSignals();
    const entry = signals.find((s) => s.kind === 'entry');
    const exit = signals.find((s) => s.kind === 'exit');
    expect(entry).toBeDefined();
    expect(exit).toBeDefined();
    // Entry precedes the exit (long-only round trip).
    expect(entry!.index).toBeLessThan(exit!.index);
  });

  it('builds price, mean and band lines with entry/exit mark-lines', () => {
    const option = getStrategyChart('rolling_average_reversion')!.buildOption() as {
      series: { name: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series).toHaveLength(3);
    expect(option.series[0].markLine?.data.length).toBeGreaterThanOrEqual(2);
  });
});

describe('atrBandChart', () => {
  it('is registered for atr_band_trend', () => {
    const chart = getStrategyChart('atr_band_trend');
    expect(chart).toBeDefined();
    expect(chart?.ariaLabel).toMatch(/atr-band trend/i);
  });

  it('detects an upper-band breakout entry followed by a below-the-average exit', () => {
    const signals = atrBandSignals();
    expect(signals.map((s) => s.kind)).toEqual(['entry', 'exit']);
    expect(signals[0].index).toBeLessThan(signals[1].index);
  });

  it('builds price, average and two bands with entry/exit mark-lines', () => {
    const option = getStrategyChart('atr_band_trend')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'mean', 'upper', 'lower']);
    expect(option.series[0].markLine?.data).toHaveLength(2);
  });
});

describe('adxChart', () => {
  it('is registered for adx_trend', () => {
    expect(getStrategyChart('adx_trend')?.ariaLabel).toMatch(/adx trend strength/i);
  });

  it('rises above the threshold in the trend and falls back in the chop', () => {
    const series = adxSeries().filter((v): v is number => v != null);
    expect(Math.max(...series)).toBeGreaterThan(20);
    expect(series[series.length - 1]).toBeLessThan(20);
    expect(adxSignals().map((s) => s.kind)).toEqual(['entry', 'exit']);
  });

  it('builds price and ADX series with entry/exit mark-lines', () => {
    const option = getStrategyChart('adx_trend')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'adx']);
    expect(option.series[0].markLine?.data).toHaveLength(2);
  });
});

describe('macdChart', () => {
  it('is registered for macd_momentum', () => {
    expect(getStrategyChart('macd_momentum')?.ariaLabel).toMatch(/macd momentum/i);
  });

  it('finds a bullish cross above zero after the pull-back', () => {
    const entry = macdEntryIndex();
    expect(entry).not.toBeNull();
    const point = macdPoints()[entry!]!;
    expect(point.macd).toBeGreaterThan(0);
    expect(point.macd).toBeGreaterThan(point.signal);
    expect(entry!).toBeGreaterThan(14); // after the dip
  });

  it('builds price, MACD and signal series with an entry mark-line', () => {
    const option = getStrategyChart('macd_momentum')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'macd', 'signal']);
    expect(option.series[0].markLine?.data).toHaveLength(1);
  });
});

describe('heikinAshiChart', () => {
  it('is registered for heikin_ashi_trend', () => {
    expect(getStrategyChart('heikin_ashi_trend')?.ariaLabel).toMatch(/heikin-ashi/i);
  });

  it('builds Heikin-Ashi candles from the bars (open = previous midpoint)', () => {
    const [first, second] = heikinAshiCandles();
    expect(second.open).toBeCloseTo((first.open + first.close) / 2);
  });

  it('enters on the first green candle and exits on the next red one', () => {
    const signals = heikinAshiSignals();
    expect(signals.map((s) => s.kind)).toEqual(['entry', 'exit']);
    expect(signals[0].index).toBeLessThan(signals[1].index);
  });

  it('builds a candlestick series with entry/exit mark-lines', () => {
    const option = getStrategyChart('heikin_ashi_trend')!.buildOption() as {
      series: { id: string; type: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => [s.id, s.type])).toEqual([['heikin-ashi', 'candlestick']]);
    expect(option.series[0].markLine?.data).toHaveLength(2);
  });
});

describe('hmaChart', () => {
  it('is registered for hma_trend', () => {
    expect(getStrategyChart('hma_trend')?.ariaLabel).toMatch(/hma trend/i);
  });

  it('equals the latest value on a straight line (proper HMA)', () => {
    const line = Array.from({ length: 20 }, (_, i) => 100 + 2 * i);
    expect(hma(line, 9)).toBeCloseTo(line[line.length - 1]);
  });

  it('enters on the rally and exits on the roll-over', () => {
    expect(hmaSignals().map((s) => s.kind)).toEqual(['entry', 'exit']);
  });

  it('builds price and two HMA series with entry/exit mark-lines', () => {
    const option = getStrategyChart('hma_trend')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'fast-hma', 'slow-hma']);
    expect(option.series[0].markLine?.data).toHaveLength(2);
  });
});

describe('maRibbonChart', () => {
  it('is registered for ma_ribbon', () => {
    expect(getStrategyChart('ma_ribbon')?.ariaLabel).toMatch(/ma ribbon/i);
  });

  it('enters where the ribbon first stacks fast > mid > slow, after the choppy base', () => {
    const entry = ribbonEntryIndex();
    expect(entry).not.toBeNull();
    const [f, m, s] = [smaSeries(3), smaSeries(6), smaSeries(10)].map((x) => x[entry!]!);
    expect(f).toBeGreaterThan(m);
    expect(m).toBeGreaterThan(s);
    expect(entry!).toBeGreaterThan(10);
  });

  it('builds price and three SMA series with an entry mark-line', () => {
    const option = getStrategyChart('ma_ribbon')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'fast', 'mid', 'slow']);
    expect(option.series[0].markLine?.data).toHaveLength(1);
  });
});

describe('vamaChart', () => {
  it('is registered for vama', () => {
    expect(getStrategyChart('vama')?.ariaLabel).toMatch(/vama/i);
  });

  it('keeps fixed smoothing at α max and lets adaptive smoothing slow down in calm bars', () => {
    const fixed = smoothingFactors(false).filter((a): a is number => a != null);
    expect(new Set(fixed)).toEqual(new Set([0.3]));
    const adaptive = smoothingFactors(true).filter((a): a is number => a != null);
    expect(Math.min(...adaptive)).toBeLessThan(0.3);
  });

  it('enters on the rally and exits on the slide', () => {
    expect(vamaSignals().map((s) => s.kind)).toEqual(['entry', 'exit']);
  });

  it('builds price and both VAMA series with entry/exit mark-lines', () => {
    const option = getStrategyChart('vama')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'vama-fixed', 'vama-adaptive']);
    expect(option.series[0].markLine?.data).toHaveLength(2);
  });
});

describe('velocityChart', () => {
  it('is registered for price_velocity_reversal', () => {
    expect(getStrategyChart('price_velocity_reversal')?.ariaLabel).toMatch(/price velocity/i);
  });

  it('enters on the slowing sell-off and exits on the first up-bar', () => {
    const signals = velocitySignals();
    expect(signals.map((s) => s.kind)).toEqual(['entry', 'exit']);
    expect(signals[0].index).toBeLessThan(signals[1].index);
  });

  it('builds price and velocity series with entry/exit mark-lines', () => {
    const option = getStrategyChart('price_velocity_reversal')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'velocity']);
    expect(option.series[0].markLine?.data).toHaveLength(2);
  });
});

describe('trendConfirmationChart', () => {
  it('is registered for trend_confirmation', () => {
    expect(getStrategyChart('trend_confirmation')?.ariaLabel).toMatch(/trend confirmation/i);
  });

  it('computes SMAs and a Wilder RSI like the backend', () => {
    expect(sma([1, 2, 3, 4], 2)).toEqual([null, 1.5, 2.5, 3.5]);
    const rising = rsi([1, 2, 3, 4, 5], 3);
    expect(rising[3]).toBe(100);
    expect(rising[2]).toBeNull();
  });

  it('enters when every leg agrees and exits when one breaks', () => {
    const signals = trendConfirmationSignals();
    expect(signals.map((s) => s.kind)).toEqual(['entry', 'exit']);
    expect(signals[0].index).toBeLessThan(signals[1].index);
  });

  it('builds price and two SMA series with entry/exit mark-lines', () => {
    const option = getStrategyChart('trend_confirmation')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'sma-fast', 'sma-slow']);
    expect(option.series[0].markLine?.data).toHaveLength(2);
  });
});

describe('volumeBreakoutChart', () => {
  it('is registered for volume_breakout', () => {
    expect(getStrategyChart('volume_breakout')?.ariaLabel).toMatch(/volume breakout/i);
  });

  it('shows exactly one volume-confirmed entry followed by one exit', () => {
    expect(volumeSignals()).toEqual([
      { index: 10, kind: 'entry' },
      { index: 21, kind: 'exit' },
    ]);
  });

  it('builds price, prior-range and volume series with entry/exit mark-lines', () => {
    const option = getStrategyChart('volume_breakout')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'prior-high', 'prior-low', 'volume']);
    expect(option.series[0].markLine?.data).toHaveLength(2);
  });
});

describe('volatilityRegimeChart', () => {
  it('is registered for volatility_regime', () => {
    expect(getStrategyChart('volatility_regime')?.ariaLabel).toMatch(/volatility regime/i);
  });

  it('shows one calm trend trade, then one volatile reversion trade', () => {
    expect(regimeSignals()).toEqual([
      { index: 11, kind: 'entry', regime: 'trend' },
      { index: 15, kind: 'exit', regime: 'trend' },
      { index: 16, kind: 'entry', regime: 'reversion' },
      { index: 18, kind: 'exit', regime: 'reversion' },
    ]);
  });

  it('builds price, HL2 and SMA series with a shaded volatile stretch', () => {
    const option = getStrategyChart('volatility_regime')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] }; markArea?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'hl2', 'sma']);
    expect(option.series[0].markLine?.data).toHaveLength(4);
    expect(option.series[0].markArea?.data).toHaveLength(1);
  });
});

describe('consensusChart', () => {
  it('is registered for signal_consensus', () => {
    expect(getStrategyChart('signal_consensus')?.ariaLabel).toMatch(/multi-signal consensus/i);
  });

  it('scores from bar 14 and enters once, on the sell-off', () => {
    const scores = consensusScores();
    expect(scores.slice(0, 14).every((s) => s === null)).toBe(true);
    // Matches the backend votes for the same closes.
    expect(scores.slice(14)).toEqual([1, -4, 1, 7, 7, 4, 1, 0, -2, -4, -5]);
    expect(consensusEntries()).toEqual([17]);
  });

  it('builds price and score series with the entry and consensus mark-lines', () => {
    const option = getStrategyChart('signal_consensus')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'score']);
    expect(option.series[0].markLine?.data).toHaveLength(1);
    expect(option.series[1].markLine?.data).toHaveLength(1);
  });
});

describe('bayesianChart', () => {
  it('is registered for bayesian_trend', () => {
    expect(getStrategyChart('bayesian_trend')?.ariaLabel).toMatch(/bayesian trend/i);
  });

  it('enters on the confident up-regime and exits on the confident down-regime', () => {
    // Matches the backend posterior for the same closes (replay 8).
    expect(bayesSignals()).toEqual([
      { index: 13, kind: 'entry' },
      { index: 27, kind: 'exit' },
    ]);
  });

  it('keeps every probability row summing to 1', () => {
    for (const p of regimeProbabilities()) {
      if (p === null) continue;
      expect(p.UP + p.FLAT + p.DOWN).toBeCloseTo(1, 9);
    }
  });

  it('builds price and stacked regime series with entry/exit and threshold mark-lines', () => {
    const option = getStrategyChart('bayesian_trend')!.buildOption() as {
      series: { id: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series.map((s) => s.id)).toEqual(['price', 'up', 'flat', 'down']);
    expect(option.series[0].markLine?.data).toHaveLength(2);
    expect(option.series[3].markLine?.data).toHaveLength(1);
  });
});
