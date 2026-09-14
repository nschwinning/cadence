import { useHealth } from '../../api/health';
import { useDashboardMetrics } from '../../api/dashboard';
import { StatTile } from '../../components/dashboard/StatTile';
import { BreakdownTile } from '../../components/dashboard/BreakdownTile';

/**
 * Dashboard — the landing view. Surfaces an at-a-glance overview of the asset
 * universe (size, eligibility, per-category/sector breakdowns), portfolio count,
 * and paper-trading activity from the live metrics endpoint, with backend health
 * shown as a compact top-right indicator.
 */

/** Turn a raw slug/key ("financial-services", "no sector") into a display label. */
function humanize(key: string): string {
  return key.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Compact backend/database status indicator shown in the header. */
function HealthIndicator() {
  const { data, isPending, isError } = useHealth();

  let dotClass = 'bg-slate-300';
  let label = 'Checking status…';
  if (isError) {
    dotClass = 'bg-red-500';
    label = 'Backend unreachable';
  } else if (!isPending && data) {
    if (data.database === 'connected') {
      dotClass = 'bg-emerald-500';
      label = 'Backend & database OK';
    } else {
      dotClass = 'bg-amber-500';
      label = 'Degraded — database disconnected';
    }
  }

  return (
    <span
      className="inline-flex items-center gap-2 text-sm text-slate-600"
      role="status"
    >
      <span
        aria-hidden="true"
        className={`inline-block h-2.5 w-2.5 rounded-full ${dotClass}`}
      />
      {label}
    </span>
  );
}

export function DashboardPage() {
  const { data, isPending, isError } = useDashboardMetrics();

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Dashboard
        </h1>
        <HealthIndicator />
      </div>

      {isPending && (
        <p role="status" aria-live="polite" className="text-lg text-slate-500">
          Loading overview metrics…
        </p>
      )}

      {isError && (
        <div
          role="alert"
          className="max-w-md rounded-lg border border-red-300 bg-red-50 p-4 text-red-800"
        >
          <p className="font-semibold">Metrics unavailable</p>
          <p className="mt-1 text-sm">
            The dashboard metrics could not be loaded. Please try again later.
          </p>
        </div>
      )}

      {!isPending && !isError && data && (
        <div className="flex flex-col gap-6">
          {/* Universe summary tiles */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatTile
              label="Universe size"
              value={data.assets.total.toLocaleString()}
              hint="total assets tracked"
            />
            <StatTile
              label="Eligible assets"
              value={data.assets.eligible.toLocaleString()}
              hint={`of ${data.assets.total.toLocaleString()} total`}
            />
            <StatTile
              label="Ineligible assets"
              value={data.assets.ineligible.toLocaleString()}
              hint="failed one or more criteria"
            />
          </div>

          {/* Activity tiles */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatTile
              label="Portfolios"
              value={data.portfolio_count.toLocaleString()}
            />
            <StatTile
              label="Active sessions"
              value={data.paper_trading.active_sessions.toLocaleString()}
              hint="paper-trading"
            />
            <StatTile
              label="Recent trades"
              value={data.paper_trading.recent_trades.toLocaleString()}
              hint="paper-trading"
            />
          </div>

          {/* Breakdown tiles */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <BreakdownTile
              title="By category"
              entries={data.assets.by_category}
              formatKey={humanize}
            />
            <BreakdownTile
              title="By sector"
              entries={data.assets.by_sector}
              formatKey={humanize}
            />
          </div>
        </div>
      )}
    </section>
  );
}

export default DashboardPage;
