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
 * Maps the pointer's horizontal position — a 0..1 ratio of the plot's rendered
 * width — to the nearest plotted point, or `null` when nothing is resolvable.
 */
export type ChartHoverResolver<T> = (ratio: number) => ChartHoverPoint<T> | null;

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
 * to a 0..1 ratio of the handler element's measured width (read fresh from the
 * event target each move so it tracks responsive layout), and that ratio is
 * handed to a chart-supplied resolver that knows its own x-projection (index vs
 * calendar-time). The resolver returns the point plus its plot-fraction position,
 * which the caller uses to place an HTML tooltip and an optional SVG marker.
 */
export function useChartHover<T>(resolve: ChartHoverResolver<T>): ChartHover<T> {
  const [active, setActive] = useState<ChartHoverPoint<T> | null>(null);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<Element>) => {
      const rect = event.currentTarget.getBoundingClientRect();
      if (rect.width <= 0 || !Number.isFinite(event.clientX)) return;
      const ratio = Math.min(
        1,
        Math.max(0, (event.clientX - rect.left) / rect.width),
      );
      setActive(resolve(ratio));
    },
    [resolve],
  );

  const onPointerLeave = useCallback(() => setActive(null), []);

  return { active, onPointerMove, onPointerLeave };
}
