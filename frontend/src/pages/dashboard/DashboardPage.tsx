import { useEffect, useRef, useState } from 'react';
import { useHealth } from '../../api/health';
import { useDashboardOverview } from '../../api/dashboard';
import type { DashboardRange } from '../../types/api';
import { RangeSelector } from './RangeSelector';
import { HeroTiles } from './HeroTiles';
import { CombinedEquityChart } from './CombinedEquityChart';
import { PortfolioLeaderboard } from './PortfolioLeaderboard';
import { AutomationPanel } from './AutomationPanel';
import { RecentActivityFeed } from './RecentActivityFeed';
import { UniverseSection } from './UniverseSection';

/**
 * Dashboard — the daily-driver landing view. A global broker-style range selector
 * drives every section: hero performance tiles, the combined equity curve (with a
 * portfolio selection that also filters the tiles and leaderboard), the portfolio
 * leaderboard, the automation panel and recent-activity feed, and the universe
 * section. All figures aggregate over ACTIVE paper-trading sessions only and come
 * from a single range-scoped overview fetch; selection changes re-aggregate on the
 * client without refetching.
 */

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
  const [range, setRange] = useState<DashboardRange>('1M');
  const { data, isPending, isError } = useDashboardOverview(range);

  const sessions = data?.sessions ?? [];
  const sessionIds = sessions.map((s) => s.id);
  const idsKey = sessionIds.join(',');

  // Selection filters the whole dashboard. New sessions default to selected;
  // deselections persist across range changes; vanished sessions are dropped.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const knownIdsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    // Snapshot the previously-known ids before updating the ref: the functional
    // state update below is deferred to render, so it must not read the ref after
    // we reassign it (that would hide every newly-arrived session).
    const known = knownIdsRef.current;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const id of sessionIds) {
        if (!known.has(id)) next.add(id);
      }
      for (const id of [...next]) {
        if (!sessionIds.includes(id)) next.delete(id);
      }
      return next;
    });
    knownIdsRef.current = new Set(sessionIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey]);

  const toggle = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectedSessions = sessions.filter((s) => selectedIds.has(s.id));

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Dashboard
          </h1>
          <RangeSelector value={range} onChange={setRange} />
        </div>
        <HealthIndicator />
      </div>

      {isPending && (
        <p role="status" aria-live="polite" className="text-lg text-slate-500">
          Loading overview…
        </p>
      )}

      {isError && (
        <div
          role="alert"
          className="max-w-md rounded-lg border border-red-300 bg-red-50 p-4 text-red-800"
        >
          <p className="font-semibold">Overview unavailable</p>
          <p className="mt-1 text-sm">
            The dashboard overview could not be loaded. Please try again later.
          </p>
        </div>
      )}

      {!isPending && !isError && data && (
        <div className="flex flex-col gap-6">
          {sessions.length === 0 && (
            <p className="text-slate-500">
              No active paper-trading sessions. Start one to see performance here.
            </p>
          )}

          <HeroTiles sessions={selectedSessions} range={range} />

          <CombinedEquityChart
            sessions={sessions}
            selectedIds={selectedIds}
            onToggle={toggle}
          />

          <PortfolioLeaderboard sessions={selectedSessions} />

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <AutomationPanel automation={data.automation} />
            <RecentActivityFeed entries={data.recent_activity} />
          </div>

          <UniverseSection
            balance={data.universe_balance}
            performers={data.universe_performers}
          />
        </div>
      )}
    </section>
  );
}

export default DashboardPage;
