import { describe, it, expect } from 'vitest';
import { formatCurrency, formatPercent, formatQuantity } from './format';

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
