import { Link } from 'react-router-dom';
import { useAdminAccount } from '../../api/admin';
import { formatRelativeTime } from '../../lib/format';
import type { DashboardTickHealth } from '../../types/api';

const CARD_CLASS = 'h-full rounded-lg border border-slate-200 bg-white shadow-sm';
const ALERT_CLASS = 'rounded border border-red-300 bg-red-50 p-2 text-sm text-red-800';

interface Consistency {
  orphans: number;
  shortfalls: number;
  shorts: number;
  unresolved: number;
}

/** Counts of account inconsistencies from the Admin account data, or null if unreadable. */
function useConsistency(): { counts: Consistency | null; pending: boolean } {
  const { data, isPending, isError } = useAdminAccount();
  if (isPending) return { counts: null, pending: true };
  if (isError || !data?.broker_available) return { counts: null, pending: false };
  const positions = data.positions ?? [];
  const count = (status: string) => positions.filter((p) => p.status === status).length;
  return {
    counts: {
      orphans: count('orphan'),
      shortfalls: count('shortfall'),
      shorts: count('short'),
      unresolved: (data.unresolved_orders ?? []).length,
    },
    pending: false,
  };
}

function CountChip({ value, label }: { value: number; label: string }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs font-medium ${
        value > 0 ? 'bg-red-100 text-red-800' : 'bg-slate-100 text-slate-500'
      }`}
    >
      {value} {label}
    </span>
  );
}

/**
 * Health — everything on the dashboard that needs the operator's attention without
 * opening a bot or the Admin page: whether the strategy-bot tick is running (stale or
 * crashed), which bots are failing (with their error), and whether the broker account
 * still matches Cadence's records (orphans, shortfalls, shorts, unresolved orders).
 * Range- and selection-independent.
 */
export function HealthSection({ tickHealth }: { tickHealth: DashboardTickHealth }) {
  const { latest, stale, failing_bots: failing } = tickHealth;
  const { counts, pending } = useConsistency();
  const inconsistent =
    counts !== null &&
    counts.orphans + counts.shortfalls + counts.shorts + counts.unresolved > 0;
  const healthy =
    !stale && !latest?.error && failing.length === 0 && counts !== null && !inconsistent;

  return (
    <div className={`${CARD_CLASS} flex flex-col gap-3 p-4`} data-testid="health-section">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900">Health</h3>
        {healthy && (
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700">
            <span aria-hidden="true" className="h-2 w-2 rounded-full bg-emerald-500" />
            All healthy
          </span>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-sm text-slate-600" data-testid="latest-tick">
          {latest
            ? `Bot ticks: last ran ${formatRelativeTime(latest.ran_at)} — ${latest.processed} processed, ${latest.failed} failed`
            : 'Bot ticks: none recorded yet'}
        </p>
        {stale && (
          <p role="alert" className={ALERT_CLASS}>
            Bot ticks have stopped: none has run for more than 15 minutes while the market is
            open.
          </p>
        )}
        {latest?.error && (
          <p role="alert" className={ALERT_CLASS}>
            The last tick crashed: {latest.error}
          </p>
        )}
        {failing.length > 0 && (
          <div role="alert" className={ALERT_CLASS}>
            <p className="font-medium">
              {failing.length} {failing.length === 1 ? 'bot is' : 'bots are'} failing
            </p>
            <ul className="mt-1 flex flex-col gap-1">
              {failing.map((bot) => (
                <li key={bot.id}>
                  <Link to={`/bots/${bot.id}`} className="font-medium underline">
                    {bot.display_name}
                  </Link>{' '}
                  — {bot.consecutive_failures} failed{' '}
                  {bot.consecutive_failures === 1 ? 'tick' : 'ticks in a row'}
                  {bot.last_failure_error && (
                    <span className="block text-xs">{bot.last_failure_error}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
        {pending ? (
          <p className="text-sm text-slate-500">Checking the broker account…</p>
        ) : counts === null ? (
          <p className="text-sm text-slate-500">Broker account unavailable</p>
        ) : inconsistent ? (
          <span className="flex flex-wrap items-center gap-1.5" data-testid="consistency">
            <span className="text-sm text-slate-600">Account:</span>
            <CountChip value={counts.orphans} label="orphans" />
            <CountChip value={counts.shortfalls} label="shortfalls" />
            <CountChip value={counts.shorts} label="shorts" />
            <CountChip value={counts.unresolved} label="unresolved orders" />
          </span>
        ) : (
          <p className="text-sm text-slate-600" data-testid="consistency">
            Account matches Cadence’s records.
          </p>
        )}
        <Link
          to="/admin"
          className="text-sm font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
        >
          Admin →
        </Link>
      </div>
    </div>
  );
}

export default HealthSection;
