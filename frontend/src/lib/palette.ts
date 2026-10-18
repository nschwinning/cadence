/**
 * Shared categorical color palette for charts that assign a distinct color per
 * series/slice by index (the session comparison chart, the dashboard breakdown
 * donuts). Keeping one source of truth means a slice and its legend entry always
 * agree, and colors stay consistent across charts. Colors cycle once exhausted.
 */
export const CATEGORICAL_PALETTE = [
  '#2563eb',
  '#059669',
  '#d97706',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
  '#db2777',
  '#65a30d',
] as const;

/** The color for the item at `index`, cycling through the palette. */
export function categoricalColor(index: number): string {
  return CATEGORICAL_PALETTE[index % CATEGORICAL_PALETTE.length];
}

/**
 * The color for a stable string `key` (for example a session id), derived from a
 * deterministic hash of the key rather than a render position. The same key always
 * maps to the same palette slot, so an item keeps its color across renders and
 * regardless of which other items are present or how they are ordered. Different
 * keys spread across the palette but may collide once there are more distinct keys
 * than palette colors — callers that need disambiguation pair the color with a label.
 */
export function colorForKey(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0;
  }
  return CATEGORICAL_PALETTE[Math.abs(hash) % CATEGORICAL_PALETTE.length];
}
