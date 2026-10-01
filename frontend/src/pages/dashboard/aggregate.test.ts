import { describe, it, expect } from 'vitest';
import {
  aggregateTotals,
  combinedSeries,
  sessionReturnPct,
  sessionValueStart,
} from './aggregate';
import { makeSession } from './fixtures';

describe('sessionValueStart / sessionReturnPct', () => {
  it('derives the start value as current_value - pnl', () => {
    const s = makeSession({ current_value: 11000, pnl: 1000 });
    expect(sessionValueStart(s)).toBe(10000);
    expect(sessionReturnPct(s)).toBeCloseTo(0.1, 10);
  });

  it('returns null when the start value is non-positive', () => {
    const s = makeSession({ current_value: 500, pnl: 500 }); // start = 0
    expect(sessionReturnPct(s)).toBeNull();
  });
});

describe('aggregateTotals (money-weighted)', () => {
  it('sums value, pnl and fees and money-weights the return', () => {
    const a = makeSession({ id: 'a', current_value: 11000, pnl: 1000, fees: 2 });
    const b = makeSession({ id: 'b', current_value: 20000, pnl: 0, fees: 3 });
    const totals = aggregateTotals([a, b]);
    expect(totals.totalValue).toBe(31000);
    expect(totals.pnl).toBe(1000);
    expect(totals.fees).toBe(5);
    // Σ pnl / Σ value_start = 1000 / (10000 + 20000)
    expect(totals.returnPct).toBeCloseTo(1000 / 30000, 10);
  });

  it('is zeroed with no sessions and never divides by zero', () => {
    const totals = aggregateTotals([]);
    expect(totals).toEqual({
      totalValue: 0,
      pnl: 0,
      fees: 0,
      returnPct: 0,
    });
  });
});

describe('combinedSeries (carry-forward summed line)', () => {
  it('sums sessions on a shared date axis', () => {
    const a = makeSession({
      id: 'a',
      points: [
        { date: '2026-06-01', value: 100 },
        { date: '2026-06-02', value: 110 },
      ],
    });
    const b = makeSession({
      id: 'b',
      points: [
        { date: '2026-06-01', value: 200 },
        { date: '2026-06-02', value: 190 },
      ],
    });
    expect(combinedSeries([a, b])).toEqual([
      { date: '2026-06-01', value: 300 },
      { date: '2026-06-02', value: 300 },
    ]);
  });

  it('carries forward a value and contributes 0 before a session starts', () => {
    const a = makeSession({
      id: 'a',
      points: [{ date: '2026-06-01', value: 100 }], // carried forward to 06-03
    });
    const b = makeSession({
      id: 'b',
      points: [{ date: '2026-06-03', value: 50 }], // absent on 06-01 → 0
    });
    expect(combinedSeries([a, b])).toEqual([
      { date: '2026-06-01', value: 100 },
      { date: '2026-06-03', value: 150 },
    ]);
  });

  it('is empty when there are no sessions or points', () => {
    expect(combinedSeries([])).toEqual([]);
  });
});
