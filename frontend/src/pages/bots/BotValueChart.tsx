import { useMemo, useState } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { useBotValueHistory } from '../../api/bots';
import type { BotValuePoint, BotValueResolution } from '../../types/api';
import {
  formatAxisTimestamp,
  formatCurrency,
  formatTooltipTimestamp,
} from '../../lib/format';
import {
  carryForwardSeries,
  todayEt,
  unionDateAxis,
} from '../../lib/carryForward';
import { EChart } from '../../components/charts/EChart';
import { FreshnessBadge, Panel } from '../paper-trading/PaperTradingSessionPage';

/** Stroke colour by the equity curve's overall direction (first → last value). */
const TREND_STROKE = {
  up: '#059669',
  down: '#dc2626',
  flat: '#64748b',
} as const;

type Trend = keyof typeof TREND_STROKE;

/** Resolution options for the switcher, in display order (coarsest intent last). */
const RESOLUTIONS: { value: BotValueResolution; label: string }[] = [
  { value: '5min', label: '5m' },
  { value: 'hourly', label: '1h' },
  { value: 'daily', label: '1D' },
  { value: 'monthly', label: '1M' },
];

/** The 5-minute and hourly resolutions plot raw intraday points (no carry-forward). */
function isIntradayResolution(resolution: BotValueResolution): boolean {
  return resolution === '5min' || resolution === 'hourly';
}

/** `dd.MM HH:mm` axis label for an intraday epoch-ms point (UTC parts, no tz drift). */
function formatIntradayAxis(ms: number): string {
  if (!Number.isFinite(ms)) return '';
  const iso = new Date(ms).toISOString();
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)} ${iso.slice(11, 16)}`;
}

/** `dd.MM.yyyy HH:mm` tooltip label for an intraday epoch-ms point. */
function formatIntradayTooltip(ms: number): string {
  if (!Number.isFinite(ms)) return '';
  const iso = new Date(ms).toISOString();
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)} ${iso.slice(11, 16)}`;
}

export function trendOf(points: BotValuePoint[]): Trend {
  const first = points[0].total_value;
  const last = points[points.length - 1].total_value;
  if (last > first) return 'up';
  if (last < first) return 'down';
  return 'flat';
}

/**
 * Build the ECharts option for a bot session's value chart: a single total-value
 * line coloured by its overall trend, on a USD y-scale and shared time x-axis.
 *
 * Daily/monthly resolutions read the end-of-day snapshot curve and are carried
 * forward flat to `horizon` (typically today in ET) so the latest non-trading day
 * reads flat at the last point instead of ending on it. Intraday resolutions
 * (`5min`/`hourly`) plot their raw timestamped points with no overnight-gap
 * carry-forward, since an intraday line should not bridge a closed market.
 */
export function buildBotValueOption(
  points: BotValuePoint[],
  { resolution, horizon }: { resolution: BotValueResolution; horizon?: string },
): EChartsCoreOption {
  const trendStroke = TREND_STROKE[trendOf(points)];
  const intraday = isIntradayResolution(resolution);

  let data: [number, number][];
  if (intraday) {
    data = points.map((p) => [Date.parse(p.timestamp), p.total_value]);
  } else {
    const dated = points.map((p) => ({
      date: p.timestamp.slice(0, 10),
      value: p.total_value,
    }));
    const axis = unionDateAxis([dated.map((d) => d.date)], horizon);
    data = carryForwardSeries(dated, axis).map((p) => [
      Date.parse(p.date),
      p.value,
    ]);
  }

  return {
    grid: { left: 64, right: 16, top: 12, bottom: 28 },
    xAxis: {
      type: 'time',
      axisLabel: {
        hideOverlap: true,
        formatter: (v: number) =>
          intraday ? formatIntradayAxis(v) : formatAxisTimestamp(v),
      },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { formatter: (v: number) => formatCurrency(v) },
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const rows = Array.isArray(params) ? params : [params];
        if (rows.length === 0) return '';
        const first = rows[0] as { axisValue?: number; value?: [number, number] };
        const ms = Number(first.axisValue);
        const header = intraday
          ? formatIntradayTooltip(ms)
          : formatTooltipTimestamp(ms);
        const raw = Array.isArray(first.value) ? first.value[1] : null;
        if (raw === null || !Number.isFinite(raw)) return header;
        return `${header}<br/>Bot value: ${formatCurrency(raw)}`;
      },
    },
    series: [
      {
        id: 'value',
        name: 'Bot value',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: trendStroke },
        data,
      },
    ],
  };
}

/**
 * A line chart of a bot session's total value over time at `resolution`. Shows a
 * dashed placeholder until there are at least two points to plot.
 */
function ValueCurve({
  points,
  resolution,
}: {
  points: BotValuePoint[];
  resolution: BotValueResolution;
}) {
  const option = useMemo(
    () =>
      points.length >= 2
        ? buildBotValueOption(points, {
            resolution,
            // Carry daily/monthly forward to today; intraday plots raw points.
            horizon: isIntradayResolution(resolution) ? undefined : todayEt(),
          })
        : null,
    [points, resolution],
  );
  if (points.length < 2 || option === null) {
    return (
      <div className="flex h-40 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400">
        Not enough history to chart yet.
      </div>
    );
  }
  return (
    <EChart
      option={option}
      height={200}
      className="w-full"
      ariaLabel={`Bot value over ${points.length} ${resolution} points`}
    />
  );
}

/** Segmented control selecting the value-chart resolution. */
function ResolutionSwitcher({
  value,
  onChange,
}: {
  value: BotValueResolution;
  onChange: (resolution: BotValueResolution) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Value chart resolution"
      className="inline-flex rounded border border-slate-200 bg-slate-50 p-0.5 text-xs"
    >
      {RESOLUTIONS.map((r) => {
        const active = r.value === value;
        return (
          <button
            key={r.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(r.value)}
            className={`rounded px-2 py-1 font-medium transition-colors ${
              active
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {r.label}
          </button>
        );
      })}
    </div>
  );
}

/** Panel showing the bot session's value as a line chart at a chosen resolution. */
export function BotValueChart({ sessionId }: { sessionId: string }) {
  const [resolution, setResolution] = useState<BotValueResolution>('daily');
  const { data, isPending, isError } = useBotValueHistory(sessionId, resolution);
  const points = data?.items ?? [];
  return (
    <Panel
      title="Bot value"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={false}
      emptyText="No value history yet."
      badge={<FreshnessBadge kind="eod" />}
    >
      <div className="space-y-3 p-4">
        <div className="flex justify-end">
          <ResolutionSwitcher value={resolution} onChange={setResolution} />
        </div>
        <ValueCurve points={points} resolution={resolution} />
      </div>
    </Panel>
  );
}

export default BotValueChart;
