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
