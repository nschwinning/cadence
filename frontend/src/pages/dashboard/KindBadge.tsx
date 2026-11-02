import type { DashboardSessionPerformance } from '../../types/api';

/** Chip styles per session kind: AI-managed portfolios vs. deterministic bots. */
const KIND_STYLES: Record<DashboardSessionPerformance['kind'], string> = {
  ai: 'bg-indigo-100 text-indigo-700',
  bot: 'bg-amber-100 text-amber-800',
};

const KIND_LABELS: Record<DashboardSessionPerformance['kind'], string> = {
  ai: 'AI',
  bot: 'Bot',
};

/**
 * A small badge marking whether a dashboard session row is an AI-managed portfolio
 * or a deterministic strategy bot, so the two kinds read apart in the shared
 * leaderboard and the combined-equity selection legend.
 */
export function KindBadge({
  kind,
}: {
  kind: DashboardSessionPerformance['kind'];
}) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide ${KIND_STYLES[kind]}`}
    >
      {KIND_LABELS[kind]}
    </span>
  );
}

export default KindBadge;
