import { describe, it, expect } from 'vitest';
import { CATEGORICAL_PALETTE, categoricalColor, colorForKey } from './palette';

describe('categoricalColor', () => {
  it('maps an index to its palette slot and cycles once exhausted', () => {
    expect(categoricalColor(0)).toBe(CATEGORICAL_PALETTE[0]);
    expect(categoricalColor(CATEGORICAL_PALETTE.length)).toBe(
      CATEGORICAL_PALETTE[0],
    );
  });
});

describe('colorForKey', () => {
  it('always maps the same key to the same palette color', () => {
    const key = '3f2b1a00-0000-4000-8000-000000000001';
    expect(colorForKey(key)).toBe(colorForKey(key));
    // The colour is independent of any surrounding order or set membership.
    expect(CATEGORICAL_PALETTE).toContain(colorForKey(key));
  });

  it('spreads different keys across the palette', () => {
    const keys = Array.from({ length: 50 }, (_, i) => `session-${i}`);
    const used = new Set(keys.map(colorForKey));
    // Many distinct keys should touch more than one palette slot (not all identical).
    expect(used.size).toBeGreaterThan(1);
    for (const color of used) expect(CATEGORICAL_PALETTE).toContain(color);
  });
});
