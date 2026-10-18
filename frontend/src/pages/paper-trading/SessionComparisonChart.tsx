import { useMemo, useState } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { useSessionsValueComparison } from '../../api/paperTrading';
import type { SessionValueComparisonSeries } from '../../types/api';
import {
  formatAxisTimestamp,
  formatCurrency,
  formatPercent,
  formatTooltipTimestamp,
} from '../../lib/format';
import { colorForKey } from '../../lib/palette';
import { EChart } from '../../components/charts/EChart';
import { Panel } from './PaperTradingSessionPage';

/** Which metric the comparison chart plots. */
export type Metric = 'return' | 'value';

/** A single plotted point: an epoch-ms timestamp and the metric-space value. */
export interface PlotPoint {
  t: number;
  value: number;
}

/** A session prepared for plotting: its colour, label, and metric-space points. */
export interface PlotSeries {
  id: string;
  label: string;
  color: string;
  points: PlotPoint[];
}

/** Format a metric-space value for the active metric. */
function formatMetric(metric: Metric, value: number): string {
  return metric === 'return' ? formatPercent(value) : formatCurrency(value);
}

/**
 * Convert the comparison response into plot series for the active metric.
 *
 * Each session's colour is keyed to its stable id (not its position), so a session
 * keeps the same colour across renders and regardless of which other sessions are
 * plotted. For the return metric a session with non-positive allocated capital
 * cannot be normalised, so it yields no points (and thus drops to legend-only).
 * Order is preserved from the input, which the API returns oldest-created first.
 */
export function buildComparisonSeries(
  sessions: SessionValueComparisonSeries[],
  metric: Metric,
): PlotSeries[] {
  return sessions.map((series) => {
    const canReturn = metric === 'return' && series.allocated_capital > 0;
    const points: PlotPoint[] =
      metric === 'value' || canReturn
        ? series.points.map((p) => ({
            t: Date.parse(p.snapshot_date),
            value:
              metric === 'value'
                ? p.total_value
                : (p.total_value - series.allocated_capital) /
                  series.allocated_capital,
          }))
        : [];
    return {
      id: series.session_id,
      label: series.label,
      color: colorForKey(series.session_id),
      points,
    };
  });
}

/** A plotted series has at least two points; legend-only sessions have fewer. */
function isPlotted(series: PlotSeries): boolean {
  return series.points.length >= 2;
}

/**
 * Build the ECharts option for the comparison plot from the already-prepared series
 * (only those with ≥2 points are drawn). The y-axis and tooltip are formatted for
 * the active metric; in the Return % view a dashed 0% baseline is pinned into the
 * domain so the break-even line is always visible. The x-axis is a shared time axis
 * with several dated ticks.
 */
export function buildComparisonOption(
  series: PlotSeries[],
  metric: Metric,
): EChartsCoreOption {
  const plottable = series.filter(isPlotted);
  const isReturn = metric === 'return';
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
      scale: !isReturn,
      // Keep 0% in view in the return metric even when every session is up (or down).
      min: isReturn
        ? (v: { min: number }) => Math.min(0, v.min)
        : undefined,
      max: isReturn
        ? (v: { max: number }) => Math.max(0, v.max)
        : undefined,
      axisLabel: { formatter: (value: number) => formatMetric(metric, value) },
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const rows = Array.isArray(params) ? params : [params];
        if (rows.length === 0) return '';
        const first = rows[0] as { axisValue?: number };
        const header = formatTooltipTimestamp(Number(first.axisValue));
        const lines = rows.map((p) => {
          const row = p as {
            seriesName?: string;
            value?: [number, number];
            marker?: string;
          };
          const value = Array.isArray(row.value) ? row.value[1] : 0;
          return `${row.marker ?? ''}${row.seriesName ?? ''}: ${formatMetric(
            metric,
            value,
          )}`;
        });
        return [header, ...lines].join('<br/>');
      },
    },
    series: plottable.map((s) => ({
      id: s.id,
      name: s.label,
      type: 'line',
      showSymbol: false,
      lineStyle: { width: 2 },
      itemStyle: { color: s.color },
      data: s.points.map((p) => [p.t, p.value]),
      ...(isReturn
        ? {
            markLine: {
              silent: true,
              symbol: 'none',
              lineStyle: { color: '#94a3b8', type: 'dashed', width: 1 },
              label: { show: false },
              data: [{ yAxis: 0 }],
            },
          }
        : {}),
    })),
  };
}

/** Colour-swatch legend mapping each session to its line colour. */
function Legend({ series, metric }: { series: PlotSeries[]; metric: Metric }) {
  return (
    <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm">
      {series.map((s) => {
        const plotted = isPlotted(s);
        const latest = s.points[s.points.length - 1];
        const summary =
          plotted && latest ? formatMetric(metric, latest.value) : 'no chart data';
        return (
          <li
            key={s.id}
            className={`flex items-center gap-2 ${
              plotted ? 'text-slate-700' : 'text-slate-400'
            }`}
          >
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="font-medium">{s.label}</span>
            <span className="text-slate-400">· {summary}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Panel comparing every non-archived session's performance over time, with a
 * %/$ toggle (defaulting to normalised return %) so sessions with different
 * capital and start dates can be compared fairly. Sessions are ordered oldest-created
 * first (from the API) and each keeps a stable colour keyed to its identity.
 */
export function SessionComparisonChart() {
  const [metric, setMetric] = useState<Metric>('return');
  const { data, isPending, isError } = useSessionsValueComparison();
  const sessions = data?.sessions ?? [];
  const series = useMemo(
    () => buildComparisonSeries(sessions, metric),
    [sessions, metric],
  );
  const plottable = series.filter(isPlotted);
  const option = useMemo(
    () => buildComparisonOption(series, metric),
    [series, metric],
  );

  return (
    <Panel
      title="Session comparison"
      count={sessions.length}
      isPending={isPending}
      isError={isError}
      isEmpty={sessions.length === 0}
      emptyText="No sessions to compare yet."
    >
      <div className="p-4">
        <div
          role="group"
          aria-label="Comparison metric"
          className="mb-4 inline-flex overflow-hidden rounded border border-slate-300 text-sm"
        >
          <button
            type="button"
            aria-pressed={metric === 'return'}
            onClick={() => setMetric('return')}
            className={`px-3 py-1 font-medium ${
              metric === 'return'
                ? 'bg-emerald-600 text-white'
                : 'bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            Return %
          </button>
          <button
            type="button"
            aria-pressed={metric === 'value'}
            onClick={() => setMetric('value')}
            className={`border-l border-slate-300 px-3 py-1 font-medium ${
              metric === 'value'
                ? 'bg-emerald-600 text-white'
                : 'bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            Value $
          </button>
        </div>
        {plottable.length === 0 ? (
          <div
            className="flex h-48 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400"
            data-testid="comparison-placeholder"
          >
            Not enough history to compare yet.
          </div>
        ) : (
          <EChart
            key={metric}
            option={option}
            height={200}
            className="w-full"
            ariaLabel={`Session comparison by ${
              metric === 'return' ? 'return percent' : 'portfolio value'
            }`}
          />
        )}
        <Legend series={series} metric={metric} />
      </div>
    </Panel>
  );
}

export default SessionComparisonChart;
