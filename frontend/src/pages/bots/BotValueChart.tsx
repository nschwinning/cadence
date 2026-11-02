import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { useBotValueHistory } from '../../api/bots';
import type { BotValueSnapshot } from '../../types/api';
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

export function trendOf(snapshots: BotValueSnapshot[]): Trend {
  const first = snapshots[0].total_value;
  const last = snapshots[snapshots.length - 1].total_value;
  if (last > first) return 'up';
  if (last < first) return 'down';
  return 'flat';
}

/**
 * Build the ECharts option for a bot session's value chart: a single total-value
 * line coloured by its overall trend, on a USD y-scale and shared time x-axis. The
 * line is carried forward flat to `horizon` (typically today in ET) so the latest
 * weekend / non-trading-day reads flat at the last snapshot instead of ending on it.
 */
export function buildBotValueOption(
  snapshots: BotValueSnapshot[],
  horizon?: string,
): EChartsCoreOption {
  const trendStroke = TREND_STROKE[trendOf(snapshots)];
  const axis = unionDateAxis([snapshots.map((s) => s.snapshot_date)], horizon);
  const value = carryForwardSeries(
    snapshots.map((s) => ({ date: s.snapshot_date, value: s.total_value })),
    axis,
  );

  return {
    grid: { left: 64, right: 16, top: 12, bottom: 28 },
    xAxis: {
      type: 'time',
      axisLabel: {
        hideOverlap: true,
        formatter: (v: number) => formatAxisTimestamp(v),
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
        const header = formatTooltipTimestamp(Number(first.axisValue));
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
        data: value.map((p) => [Date.parse(p.date), p.value]),
      },
    ],
  };
}

/**
 * A line chart of a bot session's total value over time. Shows a dashed placeholder
 * until there are at least two snapshots to plot.
 */
function ValueCurve({ snapshots }: { snapshots: BotValueSnapshot[] }) {
  const option = useMemo(
    () =>
      snapshots.length >= 2 ? buildBotValueOption(snapshots, todayEt()) : null,
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
    <EChart
      option={option}
      height={200}
      className="w-full"
      ariaLabel={`Bot value over the last ${snapshots.length} daily snapshots`}
    />
  );
}

/** Panel showing the bot session's end-of-day value as a line chart. */
export function BotValueChart({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useBotValueHistory(sessionId);
  const snapshots = data?.items ?? [];
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
      <div className="p-4">
        <ValueCurve snapshots={snapshots} />
      </div>
    </Panel>
  );
}

export default BotValueChart;
