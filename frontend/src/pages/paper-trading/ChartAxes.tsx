import type { ReactNode } from 'react';

/**
 * Layout wrapper that frames an inline-SVG plot with HTML axis tick labels.
 *
 * The charts render their plot in an SVG that uses `preserveAspectRatio="none"`,
 * which stretches the drawing horizontally to fill its container. Any SVG `<text>`
 * inside would be stretched with it and read distorted, so the tick labels live in
 * plain HTML positioned around the SVG instead: a y-axis label column to the left of
 * the plot and an x-axis label row beneath it. The SVG keeps rendering only
 * polylines, so its non-scaling-stroke behaviour and plot maths are untouched.
 *
 * `yLabels` are ordered top-to-bottom (max → min) and spread across the plot height;
 * `xLabels` mark the first and last point of the plotted domain. The y column width
 * and the x row's matching left padding are kept in sync so the x labels sit under
 * the plot's left and right edges.
 */
export function ChartAxes({
  yLabels,
  xLabels,
  children,
}: {
  yLabels: string[];
  xLabels: [string, string];
  children: ReactNode;
}) {
  return (
    <div data-testid="chart-axes">
      <div className="flex">
        <div className="flex h-40 w-16 flex-col justify-between pr-2 text-right text-xs tabular-nums text-slate-400">
          {yLabels.map((label, i) => (
            <span key={i} data-testid="chart-y-label">
              {label}
            </span>
          ))}
        </div>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
      <div className="flex justify-between pl-16 text-xs tabular-nums text-slate-400">
        <span data-testid="chart-x-label">{xLabels[0]}</span>
        <span data-testid="chart-x-label">{xLabels[1]}</span>
      </div>
    </div>
  );
}

export default ChartAxes;
