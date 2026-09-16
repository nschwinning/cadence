import axios from 'axios';
import {
  useArchiveSession,
  useUnarchiveSession,
} from '../../api/paperTrading';
import type { PaperTradingSession } from '../../types/api';

/** Map an axios error from the archive/unarchive endpoints to a message. */
function archiveErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    switch (error.response?.status) {
      case 404:
        return 'Session not found.';
      case 409:
        return 'Only a stopped session can be archived.';
      default:
        break;
    }
  }
  return 'Could not update the session. Please try again.';
}

/**
 * State + handlers for the archive action, shared between the header button
 * (upper-right corner) and the full-width feedback (errors) rendered below it.
 * Call once per session and pass the result to {@link ArchiveButton} and
 * {@link ArchiveFeedback}. The control is only meaningful for a stopped or
 * already-archived session.
 */
export function useArchiveAction(
  sessionId: string,
  session: PaperTradingSession | undefined,
) {
  const archive = useArchiveSession();
  const unarchive = useUnarchiveSession();
  const isArchived = session?.archived_at != null;
  const isStopped = session?.status === 'stopped';
  // Archivable only from stopped; unarchive is always available once archived.
  const canShow = isStopped || isArchived;
  const busy = archive.isPending || unarchive.isPending;
  const hasFeedback = archive.isError || unarchive.isError;

  const handleArchive = () => archive.mutate(sessionId);
  const handleUnarchive = () => unarchive.mutate(sessionId);

  return {
    archive,
    unarchive,
    isArchived,
    canShow,
    busy,
    hasFeedback,
    handleArchive,
    handleUnarchive,
  };
}

export type ArchiveAction = ReturnType<typeof useArchiveAction>;

/** The Archive/Unarchive trigger, sized to sit in the session header's corner. */
export function ArchiveButton({ action }: { action: ArchiveAction }) {
  const { isArchived, canShow, busy, handleArchive, handleUnarchive } = action;
  if (!canShow) return null;
  return (
    <button
      type="button"
      onClick={isArchived ? handleUnarchive : handleArchive}
      disabled={busy}
      className="rounded border border-slate-300 bg-white px-4 py-2 font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {isArchived ? 'Unarchive' : 'Archive'}
    </button>
  );
}

/** Error feedback for a failed archive/unarchive. */
export function ArchiveFeedback({ action }: { action: ArchiveAction }) {
  const { archive, unarchive } = action;
  const error = archive.error ?? unarchive.error;
  if (!archive.isError && !unarchive.isError) return null;
  return (
    <p
      role="alert"
      className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
    >
      {archiveErrorMessage(error)}
    </p>
  );
}
