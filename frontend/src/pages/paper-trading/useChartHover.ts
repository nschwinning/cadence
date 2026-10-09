import { useCallback, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';

/**
 * A resolved hover point: the chart's own payload plus where the point sits as a
 * fraction of the plot's rendered size. Fractions are of the full SVG box
 * (0 = left/top edge, 1 = right/bottom edge), so both the HTML tooltip overlay
 * and an SVG marker can be positioned from the same numbers.
 */
export interface ChartHoverPoint<T> {
  payload: T;
  /** Horizontal position of the point as a 0..1 fraction of the plot width. */
  xFraction: number;
  /** Vertical position of the point as a 0..1 fraction of the plot height. */
  yFraction: number;
}

/**
 * Maps the pointer's position — `xRatio`/`yRatio` are 0..1 fractions of the
 * plot's rendered width and height (0 = left/top edge, 1 = right/bottom edge) —
 * to the nearest plotted point, or `null` when nothing is resolvable. Single-line
 * charts need only `xRatio`; multi-line charts use `yRatio` to disambiguate which
 * overlapping line the pointer is nearest to vertically.
 */
export type ChartHoverResolver<T> = (
  xRatio: number,
  yRatio: number,
) => ChartHoverPoint<T> | null;

export interface ChartHover<T> {
  active: ChartHoverPoint<T> | null;
  onPointerMove: (event: ReactPointerEvent<Element>) => void;
  onPointerLeave: () => void;
}

/**
 * Shared hover behaviour for the dependency-free inline-SVG line charts.
 *
 * The charts render with `preserveAspectRatio="none"`, so their 0–800 viewBox
 * x-units are stretched to the container's rendered pixel width. Hit-testing
 * therefore works in rendered-pixel space: the pointer's `clientX` is converted
 * to a 0..1 ratio of the handler element's measured width (and height, read
 * fresh from the event target each move so it tracks responsive layout), and
 * those ratios are handed to a chart-supplied resolver that knows its own
 * x-projection (index vs calendar-time) and, for multi-line charts, uses the
 * vertical ratio to pick which overlapping line the pointer is nearest. The
 * resolver returns the point plus its plot-fraction position, which the caller
 * uses to place an HTML tooltip and an optional SVG marker.
 */
export function useChartHover<T>(resolve: ChartHoverResolver<T>): ChartHover<T> {
  const [active, setActive] = useState<ChartHoverPoint<T> | null>(null);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<Element>) => {
      const rect = event.currentTarget.getBoundingClientRect();
      if (rect.width <= 0 || !Number.isFinite(event.clientX)) return;
      const xRatio = Math.min(
        1,
        Math.max(0, (event.clientX - rect.left) / rect.width),
      );
      const yRatio =
        rect.height > 0 && Number.isFinite(event.clientY)
          ? Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
          : 0;
      setActive(resolve(xRatio, yRatio));
    },
    [resolve],
  );

  const onPointerLeave = useCallback(() => setActive(null), []);

  return { active, onPointerMove, onPointerLeave };
}
