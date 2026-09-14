import { useState } from 'react';
import axios from 'axios';
import {
  isTerminalEventStatus,
  useBuildStatus,
  useRebalanceSession,
} from '../../api/aiPortfolio';
import type { AIEventStatus } from '../../types/api';

/** Presentation per terminal event status. */
const TERMINAL_META: Record<
  Exclude<AIEventStatus, 'queued' | 'running'>,
  { label: string; className: string }
> = {
  succeeded: {
    label: 'Rebalance succeeded',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  },
  partial: {
    label: 'Rebalance partially succeeded',
    className: 'border-amber-200 bg-amber-50 text-amber-800',
  },
  skipped: {
    label: 'Rebalance skipped (market closed)',
    className: 'border-slate-200 bg-slate-50 text-slate-700',
  },
  failed: {
    label: 'Rebalance failed',
    className: 'border-red-300 bg-red-50 text-red-800',
  },
};

/** Map an axios error from the rebalance endpoint to a user-facing message. */
function rebalanceErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    switch (error.response?.status) {
      case 404:
        return 'Session not found.';
      case 409:
        return 'This session is not eligible for rebalancing (must be an active AI-managed session).';
      default:
        break;
    }
  }
  return 'Could not trigger a rebalance. Please try again.';
}

export function SessionRebalanceCard({ sessionId }: { sessionId: string }) {
  const rebalance = useRebalanceSession(sessionId);
  const [eventId, setEventId] = useState<string | null>(null);

  const statusQuery = useBuildStatus(eventId);
  const event = statusQuery.data;
  const status = event?.status;
  const terminal = status ? isTerminalEventStatus(status) : false;
  const running = eventId !== null && !terminal;

  const handleRebalance = () => {
    rebalance.mutate(undefined, {
      onSuccess: (res) => setEventId(res.event_id),
    });
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            AI rebalance
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Ask the AI manager to review and rebalance this session now.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRebalance}
          disabled={rebalance.isPending || running}
          aria-busy={rebalance.isPending || running}
          className="rounded bg-emerald-500 px-4 py-2 font-medium text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {rebalance.isPending || running ? 'Rebalancing…' : 'Rebalance now'}
        </button>
      </div>

      {rebalance.isError && (
        <p
          role="alert"
          className="mt-3 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          {rebalanceErrorMessage(rebalance.error)}
        </p>
      )}

      {running && (
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="mt-3 flex items-center gap-2 text-sm font-medium text-slate-600"
        >
          <span
            aria-hidden="true"
            className="h-3.5 w-3.5 rounded-full border-2 border-slate-300 border-t-emerald-500 motion-safe:animate-spin"
          />
          <span>
            {rebalance.data && !rebalance.data.started
              ? 'A rebalance was already in progress — following it…'
              : 'Rebalance in progress…'}{' '}
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
              {status ?? 'queued'}
            </span>
          </span>
        </div>
      )}

      {eventId !== null &&
        terminal &&
        event &&
        status &&
        status !== 'queued' &&
        status !== 'running' && (
          <div
            role="alert"
            className={`mt-3 rounded border px-3 py-2 text-sm ${TERMINAL_META[status].className}`}
          >
            <p className="font-semibold">{TERMINAL_META[status].label}</p>
            {event.error && (
              <p className="mt-1 whitespace-pre-wrap break-words">
                {event.error}
              </p>
            )}
            {event.actions_taken && event.actions_taken.length > 0 && (
              <p className="mt-1">
                {event.actions_taken.length} order
                {event.actions_taken.length === 1 ? '' : 's'} placed.
              </p>
            )}
          </div>
        )}
    </div>
  );
}

export default SessionRebalanceCard;
