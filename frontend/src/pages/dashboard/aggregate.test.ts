import { describe, it, expect } from 'vitest';
import {
  aggregateTotals,
  combinedSeries,
  rebaseBenchmarkLine,
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

describe('rebaseBenchmarkLine', () => {
  const start = { date: '2026-06-05', value: 10000 };

  it('rebases to the combined start using the on/before anchor and seeds the origin', () => {
    // Anchor (100) is on/before the start date; later closes scale off it.
    const line = rebaseBenchmarkLine(
      [
        { date: '2026-06-01', price: 100 }, // pre-start anchor (not plotted)
        { date: '2026-06-05', price: 110 }, // on the start date → deduped by origin
        { date: '2026-06-10', price: 121 },
      ],
      start,
    );
    expect(line).toEqual([
      { date: '2026-06-05', value: 10000 }, // origin shares the portfolio start
      { date: '2026-06-10', value: 11000 }, // 10000 × 121 / 110
    ]);
  });

  it('anchors to the earliest close when every close is after the start', () => {
    // No close on/before the start: the first available close anchors the line,
    // so it begins at that later date (no synthetic origin at the start).
    const line = rebaseBenchmarkLine(
      [
        { date: '2026-06-08', price: 200 },
        { date: '2026-06-12', price: 220 },
      ],
      start,
    );
    expect(line).toEqual([
      { date: '2026-06-08', value: 10000 }, // 10000 × 200 / 200
      { date: '2026-06-12', value: 11000 }, // 10000 × 220 / 200
    ]);
  });

  it('returns an empty line when there are no points', () => {
    expect(rebaseBenchmarkLine([], start)).toEqual([]);
  });

  it('re-rebases to a different combined start (selection change)', () => {
    // When the session selection changes, the combined curve's first point moves,
    // so the same benchmark series must re-rebase onto the new origin.
    const points = [
      { date: '2026-06-05', price: 100 },
      { date: '2026-06-10', price: 120 },
    ];
    const atTen = rebaseBenchmarkLine(points, { date: '2026-06-05', value: 10000 });
    const atTwenty = rebaseBenchmarkLine(points, { date: '2026-06-05', value: 20000 });
    expect(atTen).toEqual([
      { date: '2026-06-05', value: 10000 },
      { date: '2026-06-10', value: 12000 },
    ]);
    expect(atTwenty).toEqual([
      { date: '2026-06-05', value: 20000 },
      { date: '2026-06-10', value: 24000 },
    ]);
  });
});
