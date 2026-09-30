// A presentational page-through control: prev/next buttons around a "Page X of N"
// indicator plus a "showing A–B of total" summary. Pages are zero-indexed. It
// derives the page count from the server `total` and the table's `pageSize`, so
// the caller only tracks the current page and reacts to `onPageChange`.

const BUTTON_CLASS =
  'inline-flex items-center rounded border border-slate-300 bg-white px-3 py-1.5 ' +
  'text-sm font-medium text-slate-700 hover:bg-slate-50 ' +
  'disabled:cursor-not-allowed disabled:opacity-50';

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  label = 'rows',
}: {
  /** Current zero-indexed page. */
  page: number;
  /** Rows per page. */
  pageSize: number;
  /** Total rows across all pages (from the server). */
  total: number;
  /** Called with the target zero-indexed page when prev/next is clicked. */
  onPageChange: (page: number) => void;
  /** Plural noun for the summary line (e.g. "trades"). */
  label?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  // Clamp so a stale page (e.g. after data shrinks) still reads sensibly.
  const currentPage = Math.min(Math.max(page, 0), totalPages - 1);
  const isFirst = currentPage <= 0;
  const isLast = currentPage >= totalPages - 1;

  const first = total === 0 ? 0 : currentPage * pageSize + 1;
  const last = Math.min(total, (currentPage + 1) * pageSize);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 p-4">
      <p className="text-sm text-slate-500">
        {total === 0
          ? `No ${label}`
          : `Showing ${first}–${last} of ${total} ${label}`}
      </p>
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-500">
          Page {currentPage + 1} of {totalPages}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={BUTTON_CLASS}
            onClick={() => onPageChange(currentPage - 1)}
            disabled={isFirst}
            aria-label="Previous page"
          >
            Previous
          </button>
          <button
            type="button"
            className={BUTTON_CLASS}
            onClick={() => onPageChange(currentPage + 1)}
            disabled={isLast}
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

export default Pagination;
