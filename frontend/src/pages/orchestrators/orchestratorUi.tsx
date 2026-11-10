import { formatPercent } from '../../lib/format';

/** Status pill colours per orchestrator / bot status. */
const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  stopped: 'bg-slate-100 text-slate-700',
  archived: 'bg-slate-100 text-slate-500',
};

/** Status pill colours per decision-run status. */
const RUN_STATUS_STYLES: Record<string, string> = {
  queued: 'bg-sky-100 text-sky-800',
  running: 'bg-sky-100 text-sky-800',
  succeeded: 'bg-emerald-100 text-emerald-800',
  partial: 'bg-amber-100 text-amber-800',
  failed: 'bg-red-100 text-red-800',
  skipped: 'bg-slate-100 text-slate-600',
};

/** Human labels for the decision cadence values. */
export const CADENCE_LABELS: Record<string, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
};

export function StatusBadge({ status }: { status: string }) {
  const className = STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${className}`}
    >
      {status}
    </span>
  );
}

export function RunStatusBadge({ status }: { status: string }) {
  const className = RUN_STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${className}`}
    >
      {status}
    </span>
  );
}

/** Muted gain/loss colour for a signed figure. */
export function signClass(value: number): string {
  if (value > 0) return 'text-emerald-700';
  if (value < 0) return 'text-red-700';
  return 'text-slate-700';
}

/** A signed percentage such as "+1.25%" / "-0.40%" / "0.00%". */
export function formatSignedPercent(value: number): string {
  const text = formatPercent(value);
  return value > 0 ? `+${text}` : text;
}
