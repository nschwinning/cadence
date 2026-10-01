import { Link } from 'react-router-dom';
import type {
  DashboardPerformerEntry,
  DashboardUniverseBalance,
  DashboardUniversePerformers,
} from '../../types/api';
import { formatPercent } from '../../lib/format';
import { StatTile } from '../../components/dashboard/StatTile';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';

/**
 * The universe section: a range-independent balance summary (current composition)
 * and the range-driven best/worst market performers. The balance tiles stay put
 * as the range changes while the performer lists re-rank.
 */
export function UniverseSection({
  balance,
  performers,
}: {
  balance: DashboardUniverseBalance;
  performers: DashboardUniversePerformers;
}) {
  return (
    <div className="flex flex-col gap-6">
      <BalanceSummary balance={balance} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <PerformerList title="Top performers" entries={performers.best} />
        <PerformerList title="Worst performers" entries={performers.worst} />
      </div>
    </div>
  );
}

/** Current composition tiles — stable across range changes. */
function BalanceSummary({ balance }: { balance: DashboardUniverseBalance }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatTile
        label="Eligible assets"
        value={balance.eligible.toLocaleString()}
        hint={`${balance.ineligible.toLocaleString()} ineligible · ${balance.total.toLocaleString()} total`}
      />
      <StatTile
        label="Sectors covered"
        value={balance.sectors_count.toLocaleString()}
      />
      <StatTile
        label="Top sector"
        value={balance.top_sector_key ?? '—'}
        hint={
          balance.top_sector_key
            ? `${formatPercent(balance.top_sector_share)} of universe`
            : 'no sector data'
        }
      />
      <StatTile
        label="Top category"
        value={balance.top_category_key ?? '—'}
        hint={
          balance.top_category_key
            ? `${formatPercent(balance.top_category_share)} of universe`
            : 'no category data'
        }
      />
    </div>
  );
}

/** A ranked list of performers by market return over the range. */
function PerformerList({
  title,
  entries,
}: {
  title: string;
  entries: DashboardPerformerEntry[];
}) {
  return (
    <div className={CARD_CLASS}>
      <div className="border-b border-slate-200 p-4">
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
      </div>
      {entries.length === 0 ? (
        <p className="p-6 text-slate-500">No price history in this range yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {entries.map((e) => (
            <li
              key={e.asset_id}
              className="flex items-center gap-3 px-4 py-3 text-sm"
            >
              <Link
                to={`/assets/${encodeURIComponent(e.ticker)}`}
                className="font-medium text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {e.ticker}
              </Link>
              <span className="truncate text-slate-500">{e.name ?? ''}</span>
              <span
                className={`ml-auto tabular-nums ${
                  e.return_pct > 0
                    ? 'text-emerald-700'
                    : e.return_pct < 0
                      ? 'text-red-700'
                      : 'text-slate-700'
                }`}
              >
                {formatPercent(e.return_pct)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default UniverseSection;
