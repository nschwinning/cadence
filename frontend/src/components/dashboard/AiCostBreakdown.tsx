import type { DashboardAiCosts } from '../../types/api';
import { formatCurrency } from '../../lib/format';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';

/**
 * Per-portfolio AI (LLM) cost breakdown: one row per active portfolio with its
 * all-time cumulative spend, sorted by cost descending, plus a grand-total row.
 * All-time and range-independent — it does not react to the dashboard range or
 * the combined-equity selection.
 *
 * Degradation mirrors the per-session AI cost tile: a cost of `null` (the source
 * is unconfigured or unreachable) renders as an em dash with a "Cost tracking
 * unavailable" hint, distinct from a readable `$0.00` for a portfolio with no
 * recorded spend.
 */
export function AiCostBreakdown({ data }: { data: DashboardAiCosts }) {
  const rows = [...data.portfolios].sort((a, b) => {
    // Defensive re-sort (backend already sorts): available costs first, then
    // descending by cost; unavailable (null) costs sink to the bottom.
    const av = a.ai_cost_usd;
    const bv = b.ai_cost_usd;
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return bv - av;
  });

  const sourceUnavailable = data.total_ai_cost_usd === null;

  const renderCost = (value: number | null) =>
    value === null ? '—' : formatCurrency(value);

  return (
    <div className={CARD_CLASS}>
      <div className="flex items-baseline gap-3 border-b border-slate-200 p-4">
        <h3 className="text-lg font-semibold text-slate-900">AI cost per portfolio</h3>
        {sourceUnavailable && (
          <span className="text-sm text-slate-500">Cost tracking unavailable</span>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="p-6 text-slate-500">
          No active portfolios yet. Start one to track its AI cost here.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[320px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Portfolio</th>
                <th className="px-4 py-3 text-right">AI cost</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr
                  key={p.session_id}
                  className="border-b border-slate-100 hover:bg-slate-50"
                >
                  <td className="px-4 py-3 text-slate-700">{p.label}</td>
                  <td
                    className={`px-4 py-3 text-right tabular-nums ${
                      p.ai_cost_usd === null ? 'text-slate-400' : 'text-slate-700'
                    }`}
                  >
                    {renderCost(p.ai_cost_usd)}
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
