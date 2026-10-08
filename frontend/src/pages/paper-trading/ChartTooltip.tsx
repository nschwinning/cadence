/** One labelled value line in a chart hover tooltip. */
export interface ChartTooltipRow {
  label: string;
  value: string;
  /** Optional swatch colour keying the row to its line. */
  color?: string;
}

/**
 * A hover tooltip rendered as an HTML overlay above an inline-SVG chart.
 *
 * It is HTML rather than SVG `<text>` for the same reason `ChartAxes` renders
 * its tick labels in HTML: the charts use `preserveAspectRatio="none"`, which
 * would stretch SVG text horizontally. The host wraps the SVG in a
 * `position: relative` element; this tooltip is absolutely positioned at the
 * hovered point's plot-fraction coordinates and flips to the left of the point
 * once past the mid-line so it is not clipped at the right edge. It is
 * `pointer-events-none` so it never intercepts the pointer driving the hover.
 */
export function ChartTooltip({
  xFraction,
  yFraction,
  date,
  rows,
}: {
  xFraction: number;
  yFraction: number;
  date: string;
  rows: ChartTooltipRow[];
}) {
  const flip = xFraction > 0.5;
  return (
    <div
      role="tooltip"
      data-testid="chart-tooltip"
      className="pointer-events-none absolute z-10 min-w-[8rem] rounded border border-slate-200 bg-white/95 px-2 py-1 text-xs shadow-sm"
      style={{
        left: `${xFraction * 100}%`,
        top: `${yFraction * 100}%`,
        transform: `translate(${flip ? 'calc(-100% - 10px)' : '10px'}, -50%)`,
      }}
    >
      <div className="mb-1 font-medium text-slate-500">{date}</div>
      <ul className="space-y-0.5">
        {rows.map((row, i) => (
          <li key={i} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-slate-600">
              {row.color && (
                <span
                  aria-hidden="true"
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: row.color }}
                />
              )}
              {row.label}
            </span>
            <span className="font-semibold tabular-nums text-slate-900">
              {row.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default ChartTooltip;
