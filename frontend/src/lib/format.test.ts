import { describe, it, expect } from 'vitest';
import { formatQuantity } from './format';

describe('formatQuantity', () => {
  it('renders whole-share quantities without a fractional part', () => {
    expect(formatQuantity(10)).toBe('10');
    expect(formatQuantity(0)).toBe('0');
  });

  it('keeps a crypto fraction while trimming trailing zeros', () => {
    expect(formatQuantity(0.0512)).toBe('0.0512');
    expect(formatQuantity(1.5)).toBe('1.5');
  });

  it('caps precision at 6 fraction digits for long fractions', () => {
    expect(formatQuantity(0.05123456)).toBe('0.051235');
  });
});
