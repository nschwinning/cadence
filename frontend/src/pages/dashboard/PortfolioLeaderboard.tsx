import { Link } from 'react-router-dom';
import type { DashboardRange, DashboardSessionPerformance } from '../../types/api';
import { formatCurrency, formatPercent } from '../../lib/format';
import { sessionReturnPct } from './aggregate';
import { spanLabel } from './rangeLabel';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';

/** Muted gain/loss colour for a signed numeric cell. */
function signClass(value: number): string {
  if (value > 0) return 'text-emerald-700';
  if (value < 0) return 'text-red-700';
  return 'text-slate-700';
}

/**
 * Leaderboard of the selected active sessions, sorted by range return descending
 * (best at top; sessions without a normalisable return sink to the bottom). A
 * pure presentation of the per-session data already fetched for the tiles and
 * curve — honours the global range and the equity-curve selection.
 *
 * The Value column is point-in-time (live) and carries a live `●` marker; the
 * realised/unrealised/return/fees columns are range-scoped and sit under a
 * spanning sub-header ("Over the past month"), so the two scopes read distinctly.
 */
export function PortfolioLeaderboard({
  sessions,
  range,
}: {
  sessions: DashboardSessionPerformance[];
  range: DashboardRange;
}) {
  const ranked = [...sessions].sort((a, b) => {
    const ra = sessionReturnPct(a);
    const rb = sessionReturnPct(b);
    // Null returns (no basis) rank last; otherwise descending by return.
    if (ra === null && rb === null) return 0;
    if (ra === null) return 1;
    if (rb === null) return -1;
    return rb - ra;
  });

  const rangeSpanLabel = spanLabel(range);

  return (
    <div className={CARD_CLASS}>
      <div className="flex items-baseline gap-3 border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">
          Portfolio leaderboard
        </h2>
        {ranked.length > 0 && (
          <span className="text-sm text-slate-500">{ranked.length} selected</span>
        )}
      </div>
      {ranked.length === 0 ? (
        <p className="p-6 text-slate-500">
          No portfolios selected. Pick one from the equity curve legend above.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[0.65rem] font-semibold uppercase tracking-wide text-slate-400">
                {/* Portfolio + Value are point-in-time; the rest are range-scoped. */}
                <th className="px-4 pt-3" />
                <th className="px-4 pt-3 text-right">Now</th>
                <th className="px-4 pt-3 text-right" colSpan={4}>
                  {rangeSpanLabel}
                </th>
              </tr>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Portfolio</th>
                <th className="px-4 py-3 text-right">
                  <span className="inline-flex items-center justify-end gap-1">
                    <span
                      aria-hidden="true"
                      title="Live — marked to market against current quotes"
                      className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"
                    />
                    Value
                  </span>
                </th>
                <th className="px-4 py-3 text-right">Realised P&L</th>
                <th className="px-4 py-3 text-right">Unrealised P&L</th>
                <th className="px-4 py-3 text-right">Return</th>
                <th className="px-4 py-3 text-right">Fees</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((s) => {
                const ret = sessionReturnPct(s);
                return (
                  <tr
                    key={s.id}
                    className="border-b border-slate-100 hover:bg-slate-50"
                  >
                    <td className="px-4 py-3">
                      <Link
                        to={`/paper-trading/${s.id}`}
                        className="font-medium text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      >
                        {s.label}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                      {formatCurrency(s.current_value)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right tabular-nums ${signClass(s.realised_pnl)}`}
                    >
                      {formatCurrency(s.realised_pnl)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right tabular-nums ${signClass(s.unrealised_pnl)}`}
                    >
                      {formatCurrency(s.unrealised_pnl)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right tabular-nums ${
                        ret === null ? 'text-slate-400' : signClass(ret)
                      }`}
                    >
                      {ret === null ? '—' : formatPercent(ret)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                      {formatCurrency(s.fees)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default PortfolioLeaderboard;
