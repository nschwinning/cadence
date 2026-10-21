import { describe, it, expect } from 'vitest';
import {
  aggregateTotals,
  benchmarkDollarSeries,
  closeOnOrBefore,
  combinedSeries,
  lifetimeTotals,
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
  it('sums value, pnl, realised/unrealised and fees and money-weights the return', () => {
    const a = makeSession({
      id: 'a',
      current_value: 11000,
      pnl: 1000,
      realised_pnl: 600,
      unrealised_pnl: 400,
      fees: 2,
    });
    const b = makeSession({
      id: 'b',
      current_value: 20000,
      pnl: 0,
      realised_pnl: -100,
      unrealised_pnl: 100,
      fees: 3,
    });
    const totals = aggregateTotals([a, b]);
    expect(totals.totalValue).toBe(31000);
    expect(totals.pnl).toBe(1000);
    // Range realised/unrealised are simple dollar sums across the selection.
    expect(totals.realisedPnl).toBe(500);
    expect(totals.unrealisedPnl).toBe(500);
    expect(totals.fees).toBe(5);
    // Σ pnl / Σ value_start = 1000 / (10000 + 20000)
    expect(totals.returnPct).toBeCloseTo(1000 / 30000, 10);
  });

  it('is zeroed with no sessions and never divides by zero', () => {
    const totals = aggregateTotals([]);
    expect(totals).toEqual({
      totalValue: 0,
      pnl: 0,
      realisedPnl: 0,
      unrealisedPnl: 0,
      fees: 0,
      returnPct: 0,
    });
  });
});

describe('lifetimeTotals (since-inception value band)', () => {
  it('money-weights total return and lifetime P&L over contributed capital', () => {
    const a = makeSession({
      id: 'a',
      current_value: 12000,
      contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
      benchmark_value: 11000,
    });
    const b = makeSession({
      id: 'b',
      current_value: 21000,
      contributions: [
        { effective_date: '2026-06-01', amount: 15000 },
        { effective_date: '2026-06-10', amount: 5000 },
      ],
      benchmark_value: 20000,
    });
    const t = lifetimeTotals([a, b]);
    expect(t.totalValue).toBe(33000);
    expect(t.contributed).toBe(30000); // 10000 + 15000 + 5000
    expect(t.lifetimePnl).toBe(3000); // 33000 − 30000
    expect(t.totalReturn).toBeCloseTo(3000 / 30000, 10);
    expect(t.benchmarkValue).toBe(31000); // 11000 + 20000
    // excess = portfolio return − benchmark return = 0.1 − (31000−30000)/30000
    expect(t.excessReturn).toBeCloseTo(3000 / 30000 - 1000 / 30000, 10);
  });

  it('returns a null total return (and excess) when contributed capital is zero', () => {
    const s = makeSession({
      current_value: 5000,
      contributions: [],
      benchmark_value: 4000,
    });
    const t = lifetimeTotals([s]);
    expect(t.contributed).toBe(0);
    expect(t.lifetimePnl).toBe(5000); // still current_value − 0
    expect(t.totalReturn).toBeNull();
    expect(t.excessReturn).toBeNull();
  });

  it('propagates null benchmark/excess when any selected session is unpriceable', () => {
    const a = makeSession({
      id: 'a',
      current_value: 12000,
      contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
      benchmark_value: 11000,
    });
    const b = makeSession({
      id: 'b',
      current_value: 9000,
      contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
      benchmark_value: null, // unpriceable
    });
    const t = lifetimeTotals([a, b]);
    expect(t.totalReturn).toBeCloseTo((21000 - 20000) / 20000, 10);
    expect(t.benchmarkValue).toBeNull();
    expect(t.excessReturn).toBeNull();
  });

  it('is zeroed with no sessions and yields null return/excess', () => {
    const t = lifetimeTotals([]);
    expect(t.totalValue).toBe(0);
    expect(t.contributed).toBe(0);
    expect(t.lifetimePnl).toBe(0);
    expect(t.totalReturn).toBeNull();
    expect(t.benchmarkValue).toBe(0);
    expect(t.excessReturn).toBeNull();
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

describe('closeOnOrBefore', () => {
  const points = [
    { date: '2026-06-01', price: 100 },
    { date: '2026-06-03', price: 110 },
  ];

  it('returns the last close on/before the date (carry-forward)', () => {
    expect(closeOnOrBefore(points, '2026-06-01')).toBe(100);
    expect(closeOnOrBefore(points, '2026-06-02')).toBe(100); // carried forward
    expect(closeOnOrBefore(points, '2026-06-04')).toBe(110); // carried forward
  });

  it('returns null before the first stored close', () => {
    expect(closeOnOrBefore(points, '2026-05-31')).toBeNull();
    expect(closeOnOrBefore([], '2026-06-01')).toBeNull();
  });
});

describe('benchmarkDollarSeries (per-session buy-and-hold aggregate)', () => {
  const index = [
    { date: '2026-06-01', price: 100 },
    { date: '2026-06-02', price: 110 },
    { date: '2026-06-03', price: 100 },
    { date: '2026-06-04', price: 120 },
  ];
  const axis = ['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-04'];

  it('sums sessions and steps up on the second session open date', () => {
    const a = makeSession({
      id: 'a',
      contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
    });
    const b = makeSession({
      id: 'b',
      contributions: [{ effective_date: '2026-06-03', amount: 20000 }],
    });
    // a buys 10000/100 = 100 units on 06-01; b buys 20000/100 = 200 units on 06-03.
    expect(benchmarkDollarSeries([a, b], index, axis)).toEqual([
      { date: '2026-06-01', value: 10000 }, // 100u × 100
      { date: '2026-06-02', value: 11000 }, // 100u × 110
      { date: '2026-06-03', value: 30000 }, // (100+200)u × 100 — steps up on b's open
      { date: '2026-06-04', value: 36000 }, // 300u × 120
    ]);
  });

  it('steps up on a capital-increase contribution', () => {
    const a = makeSession({
      id: 'a',
      contributions: [
        { effective_date: '2026-06-01', amount: 10000 }, // 100 units @ 100
        { effective_date: '2026-06-03', amount: 5000 }, // +50 units @ 100
      ],
    });
    expect(benchmarkDollarSeries([a], index, axis)).toEqual([
      { date: '2026-06-01', value: 10000 }, // 100u × 100
      { date: '2026-06-02', value: 11000 }, // 100u × 110
      { date: '2026-06-03', value: 15000 }, // 150u × 100 — increase steps up
      { date: '2026-06-04', value: 18000 }, // 150u × 120
    ]);
  });

  it('is zero before the first selected session opens', () => {
    const b = makeSession({
      id: 'b',
      contributions: [{ effective_date: '2026-06-03', amount: 20000 }],
    });
    const line = benchmarkDollarSeries([b], index, axis);
    expect(line[0]).toEqual({ date: '2026-06-01', value: 0 });
    expect(line[1]).toEqual({ date: '2026-06-02', value: 0 });
    expect(line[2]).toEqual({ date: '2026-06-03', value: 20000 }); // 200u × 100
  });

  it('yields no line when the index has no stored closes', () => {
    const a = makeSession({
      id: 'a',
      contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
    });
    expect(benchmarkDollarSeries([a], [], axis)).toEqual([]);
  });

  it('yields no line when every contribution predates all closes', () => {
    // A contribution before the index's first close buys no units; with no other
    // priceable contribution the line is empty so the chart draws nothing.
    const a = makeSession({
      id: 'a',
      contributions: [{ effective_date: '2026-05-01', amount: 10000 }],
    });
    expect(benchmarkDollarSeries([a], index, axis)).toEqual([]);
  });

  it('is empty when the date axis is empty', () => {
    const a = makeSession({
      id: 'a',
      contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
    });
    expect(benchmarkDollarSeries([a], index, [])).toEqual([]);
  });
});
