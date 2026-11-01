import { describe, it, expect } from 'vitest';
import {
  todayEt,
  unionDateAxis,
  carryForwardOnto,
  carryForwardSeries,
  type DatedValue,
} from './carryForward';

const pts = (...pairs: [string, number][]): DatedValue[] =>
  pairs.map(([date, value]) => ({ date, value }));

describe('todayEt', () => {
  it('formats the ET calendar date as YYYY-MM-DD', () => {
    // 2026-01-05 05:00 UTC is still 2026-01-05 00:00 ET.
    expect(todayEt(new Date('2026-01-05T05:00:00Z'))).toBe('2026-01-05');
  });

  it('rolls back to the prior ET day for an early-UTC instant', () => {
    // 2026-01-05 02:00 UTC is 2026-01-04 21:00 ET (the day before).
    expect(todayEt(new Date('2026-01-05T02:00:00Z'))).toBe('2026-01-04');
  });

  it('is deterministic for a fixed instant', () => {
    const now = new Date('2026-03-10T15:00:00Z');
    expect(todayEt(now)).toBe(todayEt(now));
  });
});

describe('unionDateAxis', () => {
  it('builds a sorted, de-duplicated union of all series dates', () => {
    expect(
      unionDateAxis([
        ['2026-01-05', '2026-01-04'],
        ['2026-01-04', '2026-01-06'],
      ]),
    ).toEqual(['2026-01-04', '2026-01-05', '2026-01-06']);
  });

  it('appends a horizon strictly after the latest date', () => {
    expect(
      unionDateAxis([['2026-01-04', '2026-01-05']], '2026-01-07'),
    ).toEqual(['2026-01-04', '2026-01-05', '2026-01-07']);
  });

  it('does not duplicate a horizon equal to the latest date', () => {
    expect(
      unionDateAxis([['2026-01-04', '2026-01-05']], '2026-01-05'),
    ).toEqual(['2026-01-04', '2026-01-05']);
  });

  it('does not extend when the horizon precedes the latest date', () => {
    expect(
      unionDateAxis([['2026-01-04', '2026-01-09']], '2026-01-05'),
    ).toEqual(['2026-01-04', '2026-01-09']);
  });

  it('yields just the horizon for an empty input', () => {
    expect(unionDateAxis([], '2026-01-05')).toEqual(['2026-01-05']);
    expect(unionDateAxis([[]], '2026-01-05')).toEqual(['2026-01-05']);
  });

  it('yields an empty axis for an empty input and no horizon', () => {
    expect(unionDateAxis([])).toEqual([]);
    expect(unionDateAxis([[]])).toEqual([]);
  });
});

describe('carryForwardOnto', () => {
  it('carries the most recent value forward over a union axis', () => {
    const axis = ['2026-01-04', '2026-01-05', '2026-01-06', '2026-01-07'];
    expect(carryForwardOnto(pts(['2026-01-04', 100], ['2026-01-06', 120]), axis)).toEqual([
      100,
      100,
      120,
      120,
    ]);
  });

  it('fills an interior gap with the last known value', () => {
    const axis = ['2026-01-09', '2026-01-10', '2026-01-11', '2026-01-12'];
    // Friday value carried flat across Sat/Sun, then Monday's real value.
    expect(
      carryForwardOnto(pts(['2026-01-09', 50], ['2026-01-12', 55]), axis),
    ).toEqual([50, 50, 50, 55]);
  });

  it('extends flat to a trailing horizon', () => {
    const axis = ['2026-01-09', '2026-01-10', '2026-01-11'];
    expect(carryForwardOnto(pts(['2026-01-09', 50]), axis)).toEqual([50, 50, 50]);
  });

  it('returns null before the series first point (no backfill)', () => {
    const axis = ['2026-01-03', '2026-01-04', '2026-01-05'];
    expect(carryForwardOnto(pts(['2026-01-04', 100]), axis)).toEqual([
      null,
      100,
      100,
    ]);
  });

  it('sorts unordered input before carrying forward', () => {
    const axis = ['2026-01-04', '2026-01-05', '2026-01-06'];
    expect(
      carryForwardOnto(pts(['2026-01-06', 120], ['2026-01-04', 100]), axis),
    ).toEqual([100, 100, 120]);
  });

  it('handles empty points and empty axis', () => {
    expect(carryForwardOnto([], ['2026-01-04'])).toEqual([null]);
    expect(carryForwardOnto(pts(['2026-01-04', 100]), [])).toEqual([]);
  });
});

describe('carryForwardSeries', () => {
  it('drops leading dates before the first point and carries the rest forward', () => {
    const axis = ['2026-01-03', '2026-01-04', '2026-01-05', '2026-01-06'];
    expect(carryForwardSeries(pts(['2026-01-04', 100], ['2026-01-05', 110]), axis)).toEqual([
      { date: '2026-01-04', value: 100 },
      { date: '2026-01-05', value: 110 },
      { date: '2026-01-06', value: 110 },
    ]);
  });

  it('is empty when no axis date reaches the first point', () => {
    expect(
      carryForwardSeries(pts(['2026-01-10', 100]), ['2026-01-04', '2026-01-05']),
    ).toEqual([]);
  });

  it('carries a single point flat across the whole axis', () => {
    expect(
      carryForwardSeries(pts(['2026-01-04', 100]), [
        '2026-01-04',
        '2026-01-05',
        '2026-01-06',
      ]),
    ).toEqual([
      { date: '2026-01-04', value: 100 },
      { date: '2026-01-05', value: 100 },
      { date: '2026-01-06', value: 100 },
    ]);
  });

  it('is deterministic across repeated calls', () => {
    const axis = ['2026-01-04', '2026-01-05', '2026-01-06'];
    const input = pts(['2026-01-04', 100], ['2026-01-05', 110]);
    expect(carryForwardSeries(input, axis)).toEqual(
      carryForwardSeries(input, axis),
    );
  });
});
