import { useState } from 'react';
import { useSessionSectorPerformance } from '../../api/paperTrading';
import type { SessionGroupPerformance } from '../../types/api';
import { formatCurrency, formatPercent } from '../../lib/format';
import { Panel } from './PaperTradingSessionPage';

/** Which dimension the attribution rows are grouped by. */
type Grouping = 'sector' | 'category';

/** Emerald for a gain, red for a loss, slate when flat. Mirrors the KPI styling. */
function pnlClass(value: number): string {
  if (value > 0) return 'text-emerald-700';
  if (value < 0) return 'text-red-700';
  return 'text-slate-700';
}

/**
 * A single attribution row: the group's total P&L as a diverging bar (gain to the
 * right in emerald, loss to the left in red, anchored at a shared centre line) plus
 * its market value and return. P&L and return are coloured by sign; a group with no
 * cost basis (null return) reads "Not available" rather than a misleading 0%.
 */
function GroupRow({
  group,
  maxAbsPnl,
}: {
  group: SessionGroupPerformance;
  maxAbsPnl: number;
}) {
  // Bar width is the group's |total P&L| as a share of the largest |total P&L| in
  // the current grouping, scaled to the half-width on its side of the centre line.
  const widthPct = maxAbsPnl > 0 ? (Math.abs(group.total_pnl) / maxAbsPnl) * 50 : 0;
  const isGain = group.total_pnl > 0;
  const isLoss = group.total_pnl < 0;

  return (
    <tr className="border-b border-slate-100">
      <td className="px-4 py-3 font-medium capitalize text-slate-700">
        {group.key}
      </td>
      <td className="px-4 py-3">
        <div
          className="flex h-4 items-stretch"
          role="presentation"
          aria-hidden="true"
        >
          <div className="flex w-1/2 justify-end">
            {isLoss && (
              <div
                className="rounded-l bg-red-500"
                style={{ width: `${widthPct}%` }}
              />
            )}
          </div>
          <div className="w-px bg-slate-300" />
          <div className="flex w-1/2 justify-start">
            {isGain && (
              <div
                className="rounded-r bg-emerald-500"
                style={{ width: `${widthPct}%` }}
              />
            )}
          </div>
        </div>
      </td>
      <td
        className={`px-4 py-3 text-right tabular-nums font-medium ${pnlClass(group.total_pnl)}`}
      >
        {formatCurrency(group.total_pnl)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-500">
        {formatCurrency(group.market_value)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums">
        {group.return_pct === null ? (
          <span className="text-slate-400">Not available</span>
        ) : (
          <span className={pnlClass(group.return_pct)}>
            {formatPercent(group.return_pct)}
          </span>
        )}
      </td>
    </tr>
  );
}

/** The attribution table for one grouping (sector or category). */
function GroupTable({ rows }: { rows: SessionGroupPerformance[] }) {
  const maxAbsPnl = rows.reduce(
    (max, row) => Math.max(max, Math.abs(row.total_pnl)),
    0,
  );
  return (
    <table className="w-full min-w-[640px] border-collapse text-sm">
      <thead>
        <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
          <th className="px-4 py-3">Group</th>
          <th className="px-4 py-3">Total P&amp;L</th>
          <th className="px-4 py-3 text-right">P&amp;L</th>
          <th className="px-4 py-3 text-right">Market value</th>
          <th className="px-4 py-3 text-right">Return</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <GroupRow key={row.key} group={row} maxAbsPnl={maxAbsPnl} />
        ))}
      </tbody>
    </table>
  );
}

/**
 * Session-detail card attributing the session's total P&L (realised + unrealised)
 * across sectors and asset categories, with a by-sector / by-category toggle. P&L
 * can be negative, so it uses signed diverging bars rather than a donut; each row
 * also shows market value (weight context) and a return, with a null return shown
 * as "Not available".
 */
export function SessionSectorPerformanceCard({
  sessionId,
}: {
  sessionId: string;
}) {
  const [grouping, setGrouping] = useState<Grouping>('sector');
  const { data, isPending, isError } = useSessionSectorPerformance(sessionId);

  const rows =
    data === undefined
      ? []
      : grouping === 'sector'
        ? data.by_sector
        : data.by_category;
  const isEmpty =
    data !== undefined &&
    data.by_sector.length === 0 &&
    data.by_category.length === 0;

  return (
    <Panel
      title="Performance attribution"
      count={rows.length}
      isPending={isPending}
      isError={isError}
      isEmpty={isEmpty}
      emptyText="No positions to attribute yet."
    >
      <div className="p-4">
        <div
          role="group"
          aria-label="Attribution grouping"
          className="mb-4 inline-flex overflow-hidden rounded border border-slate-300 text-sm"
        >
          <button
            type="button"
            aria-pressed={grouping === 'sector'}
            onClick={() => setGrouping('sector')}
            className={`px-3 py-1 font-medium ${
              grouping === 'sector'
                ? 'bg-emerald-600 text-white'
                : 'bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            By sector
          </button>
          <button
            type="button"
            aria-pressed={grouping === 'category'}
            onClick={() => setGrouping('category')}
            className={`border-l border-slate-300 px-3 py-1 font-medium ${
              grouping === 'category'
                ? 'bg-emerald-600 text-white'
                : 'bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            By category
          </button>
        </div>
        <GroupTable rows={rows} />
      </div>
    </Panel>
  );
}

export default SessionSectorPerformanceCard;
