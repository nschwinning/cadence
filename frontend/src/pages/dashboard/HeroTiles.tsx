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
 * The point-in-time value tile for the Portfolio value band: the live net-asset
 * value summed across the selected sessions. Not range-scoped — it reads the same
 * regardless of the selected range — so it lives in its own band, visually split
 * from the range-scoped performance figures.
 */
export function ValueTiles({
  sessions,
}: {
  sessions: DashboardSessionPerformance[];
}) {
  const totals = aggregateTotals(sessions);
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatTile
        label="Total value"
        value={formatCurrency(totals.totalValue)}
        hint={`${sessions.length} selected ${
          sessions.length === 1 ? 'portfolio' : 'portfolios'
        } · point-in-time`}
      />
    </div>
  );
}

/**
 * The range-scoped performance tiles for the Performance band: realised P&L,
 * unrealised P&L, money-weighted return, and fees — all relative to the selected
 * range and re-derived client-side from the selected sessions, so toggling the
 * equity-curve legend updates them without a refetch. Realised and unrealised are
 * sign-distinguished and replace the single range ΔNAV P&L tile.
 */
export function PerformanceTiles({
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
        label="Realised P&L"
        value={
          <span className={signClass(totals.realisedPnl)}>
            {formatCurrency(totals.realisedPnl)}
          </span>
        }
        hint={hint}
      />
      <StatTile
        label="Unrealised P&L"
        value={
          <span className={signClass(totals.unrealisedPnl)}>
            {formatCurrency(totals.unrealisedPnl)}
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
      <StatTile label="Fees" value={formatCurrency(totals.fees)} hint={hint} />
    </div>
  );
}
