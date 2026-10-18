import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { useSessionValueHistory } from '../../api/paperTrading';
import type { SessionValueSnapshot } from '../../types/api';
import {
  formatAxisTimestamp,
  formatCurrency,
  formatTooltipTimestamp,
} from '../../lib/format';
import { EChart } from '../../components/charts/EChart';
import { FreshnessBadge, Panel } from './PaperTradingSessionPage';

/** Stroke colour by the equity curve's overall direction (first → last value). */
const TREND_STROKE = {
  up: '#059669',
  down: '#dc2626',
  flat: '#64748b',
} as const;

type Trend = keyof typeof TREND_STROKE;

/** Stroke colour for the benchmark overlay line (neutral amber, distinct from trend). */
const BENCHMARK_STROKE = '#d97706';

export function trendOf(snapshots: SessionValueSnapshot[]): Trend {
  const first = snapshots[0].total_value;
  const last = snapshots[snapshots.length - 1].total_value;
  if (last > first) return 'up';
  if (last < first) return 'down';
  return 'flat';
}

/** Whether the benchmark overlay has enough non-null points to draw. */
export function benchmarkDrawnFor(snapshots: SessionValueSnapshot[]): boolean {
  return (
    snapshots.filter((s) => s.benchmark_value !== null).length >= 2
  );
}

/**
 * Build the ECharts option for a session's value chart: the portfolio-value line
 * (coloured by its overall trend) and, when it has enough non-null points, the
 * benchmark overlay (dashed amber) on the same USD y-scale and shared time x-axis
 * (with several dated ticks). The tooltip reports each line's value at the hovered
 * date, skipping the benchmark row where no benchmark value exists.
 */
export function buildValueOption(
  snapshots: SessionValueSnapshot[],
): EChartsCoreOption {
  const trendStroke = TREND_STROKE[trendOf(snapshots)];
  const benchmarkDrawn = benchmarkDrawnFor(snapshots);

  const series: Array<Record<string, unknown>> = [
    {
      id: 'portfolio',
      name: 'Portfolio value',
      type: 'line',
      showSymbol: false,
      lineStyle: { width: 2 },
      itemStyle: { color: trendStroke },
      data: snapshots.map((s) => [Date.parse(s.snapshot_date), s.total_value]),
    },
  ];
  if (benchmarkDrawn) {
    series.push({
      id: 'benchmark',
      name: 'Benchmark',
      type: 'line',
      showSymbol: false,
      lineStyle: { width: 1.5, type: 'dashed' },
      itemStyle: { color: BENCHMARK_STROKE },
      connectNulls: false,
      data: snapshots.map((s) => [
        Date.parse(s.snapshot_date),
        s.benchmark_value,
      ]),
    });
  }

  return {
    grid: { left: 64, right: 16, top: 12, bottom: 28 },
    xAxis: {
      type: 'time',
      axisLabel: {
        hideOverlap: true,
        formatter: (value: number) => formatAxisTimestamp(value),
      },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { formatter: (value: number) => formatCurrency(value) },
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const rows = Array.isArray(params) ? params : [params];
        if (rows.length === 0) return '';
        const first = rows[0] as { axisValue?: number };
        const header = formatTooltipTimestamp(Number(first.axisValue));
        const lines = rows
          .map((p) => {
            const row = p as {
              seriesName?: string;
              value?: [number, number | null];
              marker?: string;
            };
            const raw = Array.isArray(row.value) ? row.value[1] : null;
            if (raw === null || !Number.isFinite(raw)) return null;
            return `${row.marker ?? ''}${row.seriesName ?? ''}: ${formatCurrency(
              raw,
            )}`;
          })
          .filter((line): line is string => line !== null);
        return [header, ...lines].join('<br/>');
      },
    },
    series,
  };
}

/**
 * A line chart of a session's total value over time. Shows a dashed placeholder
 * until there are at least two snapshots to plot.
 */
function ValueCurve({ snapshots }: { snapshots: SessionValueSnapshot[] }) {
  // Only build the option once there is something to plot; buildValueOption reads
  // the first/last snapshot for the trend colour and would throw on an empty list.
  const option = useMemo(
    () => (snapshots.length >= 2 ? buildValueOption(snapshots) : null),
    [snapshots],
  );
  if (snapshots.length < 2 || option === null) {
    return (
      <div className="flex h-40 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400">
        Not enough history to chart yet.
      </div>
    );
  }
  return (
    <div>
      <EChart
        option={option}
        height={200}
        className="w-full"
        ariaLabel={`Portfolio value over the last ${snapshots.length} daily snapshots`}
      />
      <ValueLegend
        trendStroke={TREND_STROKE[trendOf(snapshots)]}
        benchmarkDrawn={benchmarkDrawnFor(snapshots)}
      />
    </div>
  );
}

/**
 * Legend naming the two lines on the value chart. The benchmark entry appears only
 * when the benchmark line is actually drawn, so the legend never implies a line that
 * is not on the chart.
 */
function ValueLegend({
  trendStroke,
  benchmarkDrawn,
}: {
  trendStroke: string;
  benchmarkDrawn: boolean;
}) {
  return (
    <ul
      className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-700"
      data-testid="value-legend"
    >
      <li className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-2.5 w-2.5 rounded-full"
          style={{ backgroundColor: trendStroke }}
        />
        <span className="font-medium">Portfolio value</span>
      </li>
      {benchmarkDrawn && (
        <li className="flex items-center gap-2" data-testid="benchmark-legend">
          <span
            aria-hidden="true"
            className="inline-block h-0.5 w-4"
            style={{
              backgroundImage: `repeating-linear-gradient(to right, ${BENCHMARK_STROKE} 0 4px, transparent 4px 7px)`,
            }}
          />
          <span className="font-medium">Benchmark</span>
        </li>
      )}
    </ul>
  );
}

/** Panel showing the session's end-of-day portfolio value as a line chart. */
export function SessionValueChart({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useSessionValueHistory(sessionId);
  const snapshots = data?.items ?? [];
  return (
    <Panel
      title="Portfolio value"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={false}
      emptyText="No value history yet."
      badge={<FreshnessBadge kind="eod" />}
    >
      <div className="p-4">
        <ValueCurve snapshots={snapshots} />
      </div>
    </Panel>
  );
}

export default SessionValueChart;
