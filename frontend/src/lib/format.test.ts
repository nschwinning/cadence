import { describe, it, expect } from 'vitest';
import {
  formatAge,
  formatAxisDate,
  formatCurrency,
  formatPercent,
  formatQuantity,
  formatTooltipDate,
} from './format';

describe('formatQuantity', () => {
  it('keeps whole shares whole and trims fractional trailing zeros', () => {
    expect(formatQuantity(10)).toBe('10');
    expect(formatQuantity(0.05123456)).toBe('0.051235');
  });
});

describe('formatCurrency', () => {
  it('formats positive, negative, and zero as USD with two decimals', () => {
    expect(formatCurrency(1234.5)).toBe('$1,234.50');
    expect(formatCurrency(-1234.5)).toBe('-$1,234.50');
    expect(formatCurrency(0)).toBe('$0.00');
  });
});

describe('formatPercent', () => {
  it('formats a fraction as a percentage with two decimals by default', () => {
    expect(formatPercent(0.032)).toBe('3.20%');
    expect(formatPercent(-0.015)).toBe('-1.50%');
    expect(formatPercent(0)).toBe('0.00%');
  });

  it('honours a custom fraction-digit count', () => {
    expect(formatPercent(0.032, 1)).toBe('3.2%');
  });
});

describe('formatAge', () => {
  const now = new Date('2026-06-15T12:00:00Z');
  const daysBefore = (n: number) =>
    new Date(now.getTime() - n * 86_400_000).toISOString();

  it('reads same-day as today', () => {
    expect(formatAge(daysBefore(0), now)).toBe('today');
    // Earlier the same calendar distance (a few hours) is still today.
    expect(formatAge(new Date(now.getTime() - 3 * 3_600_000), now)).toBe('today');
  });

  it('reads recent ages in whole days below a week', () => {
    expect(formatAge(daysBefore(1), now)).toBe('1d');
    expect(formatAge(daysBefore(6), now)).toBe('6d');
  });

  it('rolls over to weeks at seven days', () => {
    expect(formatAge(daysBefore(7), now)).toBe('1w');
    expect(formatAge(daysBefore(20), now)).toBe('2w');
    expect(formatAge(daysBefore(29), now)).toBe('4w');
  });

  it('rolls over to months at thirty days', () => {
    expect(formatAge(daysBefore(30), now)).toBe('1mo');
    expect(formatAge(daysBefore(90), now)).toBe('3mo');
  });

  it('rolls over to years at a full year', () => {
    expect(formatAge(daysBefore(365), now)).toBe('1y');
    expect(formatAge(daysBefore(900), now)).toBe('2y');
  });

  it('accepts a Date and clamps a future time to today', () => {
    expect(formatAge(new Date(daysBefore(2)), now)).toBe('2d');
    expect(formatAge(new Date(now.getTime() + 86_400_000), now)).toBe('today');
  });

  it('falls back to the raw string for an unparseable input', () => {
    expect(formatAge('not-a-date', now)).toBe('not-a-date');
  });
});

describe('formatAxisDate', () => {
  it('formats an ISO date as a short German dd.MM label', () => {
    expect(formatAxisDate('2026-01-04')).toBe('04.01');
    expect(formatAxisDate('2026-12-31')).toBe('31.12');
  });

  it('does not shift the day from timezone interpretation', () => {
    // A UTC-midnight date can render as the previous day under local time; the
    // part-based parse keeps 2026-01-01 as 01.01 regardless of the runner's zone.
    expect(formatAxisDate('2026-01-01')).toBe('01.01');
  });

  it('falls back to the raw string when the shape is unexpected', () => {
    expect(formatAxisDate('not-a-date')).toBe('not-a-date');
  });
});

describe('formatTooltipDate', () => {
  it('formats an ISO date as a fuller German dd.MM.yyyy label', () => {
    expect(formatTooltipDate('2026-01-04')).toBe('04.01.2026');
    expect(formatTooltipDate('2026-12-31')).toBe('31.12.2026');
  });

  it('does not shift the day from timezone interpretation', () => {
    // Part-based parsing keeps a UTC-midnight date on its own calendar day
    // regardless of the runner's local zone.
    expect(formatTooltipDate('2026-01-01')).toBe('01.01.2026');
  });

  it('falls back to the raw string when the shape is unexpected', () => {
    expect(formatTooltipDate('not-a-date')).toBe('not-a-date');
  });
});
