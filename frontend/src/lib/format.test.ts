import { describe, it, expect } from 'vitest';
import {
  formatAxisDate,
  formatCurrency,
  formatPercent,
  formatQuantity,
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

describe('formatAxisDate', () => {
  it('formats an ISO date as a short M/D label', () => {
    expect(formatAxisDate('2026-01-04')).toBe('1/4');
    expect(formatAxisDate('2026-12-31')).toBe('12/31');
  });

  it('does not shift the day from timezone interpretation', () => {
    // A UTC-midnight date can render as the previous day under local time; the
    // part-based parse keeps 2026-01-01 as 1/1 regardless of the runner's zone.
    expect(formatAxisDate('2026-01-01')).toBe('1/1');
  });

  it('falls back to the raw string when the shape is unexpected', () => {
    expect(formatAxisDate('not-a-date')).toBe('not-a-date');
  });
});
