import type { DashboardRange, DashboardSessionPerformance } from '../../types/api';
import { formatCurrency, formatPercent } from '../../lib/format';
import { StatTile } from '../../components/dashboard/StatTile';
import { aggregateTotals } from './aggregate';

/** Muted colour for a signed figure: emerald up, red down, slate flat. */
function signClass(value: number): string {
  if (value > 0) return 'text-emerald-700';
  if (value < 0) return 'text-red-700';
  return 'text-slate-900';
}

const RANGE_LABEL: Record<DashboardRange, string> = {
  '1D': 'today',
  '1W': 'past week',
  '1M': 'past month',
  YTD: 'year to date',
  '1Y': 'past year',
  Max: 'since inception',
};

/**
 * The hero performance tiles: total value, range P&L, money-weighted range
 * return, and range fees — all re-derived client-side from the selected
 * sessions, so toggling the equity-curve legend updates them without a refetch.
 */
export function HeroTiles({
  sessions,
  range,
}: {
  sessions: DashboardSessionPerformance[];
  range: DashboardRange;
}) {
  const totals = aggregateTotals(sessions);
  const hint = RANGE_LABEL[range];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatTile
        label="Total value"
        value={formatCurrency(totals.totalValue)}
        hint={`${sessions.length} selected ${
          sessions.length === 1 ? 'portfolio' : 'portfolios'
        }`}
      />
      <StatTile
        label="P&L"
        value={
          <span className={signClass(totals.pnl)}>
            {formatCurrency(totals.pnl)}
          </span>
        }
        hint={hint}
      />
      <StatTile
        label="Return"
        value={
          <span className={signClass(totals.returnPct)}>
            {formatPercent(totals.returnPct)}
          </span>
        }
        hint={`money-weighted · ${hint}`}
      />
      <StatTile
        label="Fees"
        value={formatCurrency(totals.fees)}
        hint={hint}
      />
    </div>
  );
}

export default HeroTiles;
