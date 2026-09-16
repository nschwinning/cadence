import { useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { useCloseSession } from '../../api/aiPortfolio';
import type { AIPortfolioRunDetail } from '../../types/api';

/** Format a EUR value. */
const eur = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 2,
});

/** Map an axios error from the close endpoint to a user-facing message. */
function closeErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    switch (error.response?.status) {
      case 404:
        return 'Session not found.';
      case 409:
        return 'This session cannot be closed (must be an active AI-managed session with no rebalance in progress).';
      default:
        break;
    }
  }
  return 'Could not close the portfolio. Please try again.';
}

/** The outcome summary shown after a successful close. */
function CloseResult({ result }: { result: AIPortfolioRunDetail }) {
  const closedCount = result.closed_positions.length;
  const realized = result.closed_positions.reduce(
    (sum, p) => sum + p.realized_pnl,
    0,
  );
  const skipped = (result.event.actions_taken ?? []).filter(
    (a) => a.executed === false,
  ).length;

  return (
    <div
      role="alert"
      className="mt-3 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
    >
      <p className="font-semibold">Portfolio closed</p>
      <p className="mt-1">
        {closedCount} position{closedCount === 1 ? '' : 's'} liquidated · realized
        P&amp;L {eur.format(realized)}
        {skipped > 0
          ? ` · ${skipped} order${skipped === 1 ? '' : 's'} could not be closed`
          : ''}
        .
      </p>
      <Link
        to={`/runs/${result.event.id}`}
        className="mt-1 inline-block font-medium text-emerald-700 underline hover:text-emerald-800"
      >
        View the close run
      </Link>
    </div>
  );
}

/**
 * Close-portfolio action for an AI-managed session: liquidates every open
 * position immediately and stops the session. Guarded behind an explicit confirm
 * step because it is irreversible. The button is only enabled for an active
 * session; a stopped/paused session shows a disabled note instead.
 */
export function SessionCloseCard({
  sessionId,
  status,
}: {
  sessionId: string;
  status: string | undefined;
}) {
  const close = useCloseSession(sessionId);
  const [confirming, setConfirming] = useState(false);
  const isActive = status === 'active';
  const done = close.isSuccess;

  const handleConfirm = () => {
    close.mutate(undefined, { onSuccess: () => setConfirming(false) });
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Close portfolio
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Immediately sell all open positions and stop this portfolio. This
            can&rsquo;t be undone.
          </p>
        </div>
        {!confirming && !done && (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={!isActive || close.isPending}
            className="rounded border border-red-300 bg-white px-4 py-2 font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Close portfolio
          </button>
        )}
      </div>

      {!isActive && !done && (
        <p className="mt-3 text-sm text-slate-500">
          Only an active portfolio can be closed
          {status ? ` (this one is ${status})` : ''}.
        </p>
      )}

      {confirming && (
        <div className="mt-3 flex flex-col gap-3 rounded border border-red-200 bg-red-50 p-3">
          <p className="text-sm text-red-800">
            This liquidates every open position at market and stops the
            portfolio. Are you sure?
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleConfirm}
              disabled={close.isPending}
              aria-busy={close.isPending}
              className="rounded bg-red-600 px-4 py-2 font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {close.isPending ? 'Closing…' : 'Confirm close'}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={close.isPending}
              className="rounded border border-slate-300 px-4 py-2 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {close.isError && (
        <p
          role="alert"
          className="mt-3 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          {closeErrorMessage(close.error)}
        </p>
      )}

      {done && close.data && <CloseResult result={close.data} />}
    </div>
  );
}

export default SessionCloseCard;
