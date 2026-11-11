import { Link } from 'react-router-dom';
import type { DashboardAiCosts } from '../../types/api';
import { formatCurrency } from '../../lib/format';
import { KindBadge } from '../../pages/dashboard/KindBadge';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';

/** One row of the breakdown: a portfolio or a bot orchestrator. */
interface CostRow {
  key: string;
  label: string;
  cost: number | null;
  /** Every row links to its detail view and carries a kind badge. */
  kind: 'ai' | 'orchestrator';
  href: string;
}

/**
 * AI (LLM) cost breakdown: one row per active portfolio and per active bot
 * orchestrator with its all-time cumulative spend, sorted by cost descending,
 * plus a grand-total row. Each row links to its portfolio or orchestrator and
 * carries the same kind badge as the leaderboard. All-time and range-independent — it does not react to the
 * dashboard range or the combined-equity selection.
 *
 * Degradation mirrors the per-session AI cost tile: a cost of `null` (the source
 * is unconfigured or unreachable) renders as an em dash with a "Cost tracking
 * unavailable" hint, distinct from a readable `$0.00` for a row with no recorded
 * spend.
 */
export function AiCostBreakdown({ data }: { data: DashboardAiCosts }) {
  const rows: CostRow[] = [
    ...data.portfolios.map((p) => ({
      key: `portfolio-${p.session_id}`,
      label: p.label,
      cost: p.ai_cost_usd,
      kind: 'ai' as const,
      href: `/portfolios/${p.session_id}`,
    })),
    ...(data.orchestrators ?? []).map((o) => ({
      key: `orchestrator-${o.orchestrator_id}`,
      label: o.label,
      cost: o.ai_cost_usd,
      kind: 'orchestrator' as const,
      href: `/orchestrators/${o.orchestrator_id}`,
    })),
  ].sort((a, b) => {
    // Available costs first, then descending by cost; unavailable (null) costs
    // sink to the bottom.
    if (a.cost === null && b.cost === null) return 0;
    if (a.cost === null) return 1;
    if (b.cost === null) return -1;
    return b.cost - a.cost;
  });

  const sourceUnavailable = data.total_ai_cost_usd === null;

  const renderCost = (value: number | null) =>
    value === null ? '—' : formatCurrency(value);

  return (
    <div className={CARD_CLASS}>
      <div className="flex items-baseline gap-3 border-b border-slate-200 p-4">
        <h3 className="text-lg font-semibold text-slate-900">
          AI cost per portfolio &amp; orchestrator
        </h3>
        {sourceUnavailable && (
          <span className="text-sm text-slate-500">Cost tracking unavailable</span>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="p-6 text-slate-500">
          No active portfolios or orchestrators yet. Start one to track its AI cost
          here.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[320px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Portfolio / orchestrator</th>
                <th className="px-4 py-3 text-right">AI cost</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-700">
                    <span className="inline-flex flex-wrap items-center gap-2">
                      <Link
                        to={row.href}
                        className="font-medium text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      >
                        {row.label}
                      </Link>
                      <KindBadge kind={row.kind} />
                    </span>
                  </td>
                  <td
                    className={`px-4 py-3 text-right tabular-nums ${
                      row.cost === null ? 'text-slate-400' : 'text-slate-700'
                    }`}
                  >
                    {renderCost(row.cost)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-slate-200 bg-slate-50 font-semibold">
                <td className="px-4 py-3 text-slate-900">Total</td>
                <td
                  className={`px-4 py-3 text-right tabular-nums ${
                    data.total_ai_cost_usd === null
                      ? 'text-slate-400'
                      : 'text-slate-900'
                  }`}
                >
                  {renderCost(data.total_ai_cost_usd)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

export default AiCostBreakdown;
