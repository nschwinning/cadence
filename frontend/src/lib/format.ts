/** Shared display formatters kept independent of any single page. */

/**
 * Formats an instrument quantity for display. Equities trade in whole shares
 * while crypto is fractional, so we allow up to 6 fraction digits and trim
 * trailing zeros: a whole `10` stays `10`, and a fractional `0.05123456`
 * reads as `0.051235` rather than a misleading `0` or `10.000000`.
 */
const quantityFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 6,
});

export function formatQuantity(value: number): string {
  return quantityFormatter.format(value);
}

/**
 * Format a monetary value as USD with two fraction digits (e.g. `-$1,234.50`).
 * USD matches the brokerage's (Alpaca) settlement currency; the underlying
 * stored numbers are unchanged — this is presentational only.
 */
const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

export function formatCurrency(value: number): string {
  return currencyFormatter.format(value);
}

/**
 * Format a fraction as a percentage string (e.g. `0.032` -> `3.20%`). Negative
 * and zero values format naturally (`-1.50%`, `0.00%`); callers convey gain/loss
 * colour separately.
 */
export function formatPercent(value: number, fractionDigits = 2): string {
  return `${(value * 100).toFixed(fractionDigits)}%`;
}

/**
 * Format an ISO `YYYY-MM-DD` date as a short `M/D` axis label. Parses the date
 * parts directly rather than via `new Date(iso)` so the label never shifts a day
 * from local-timezone interpretation of a UTC-midnight date. Falls back to the
 * raw string if it is not in the expected shape.
 */
export function formatAxisDate(iso: string): string {
  const parts = iso.split('-');
  if (parts.length !== 3) return iso;
  const month = Number(parts[1]);
  const day = Number(parts[2]);
  if (!Number.isFinite(month) || !Number.isFinite(day)) return iso;
  return `${month}/${day}`;
}

/**
 * Format an ISO datetime as a compact, human relative time (e.g. `just now`,
 * `5m ago`, `3h ago`, `2d ago`), falling back to an absolute locale date for
 * anything older than a week or a future time. Used by the dashboard automation
 * panel and activity feed where a precise timestamp is less useful than recency.
 */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const ms = then.getTime();
  if (!Number.isFinite(ms)) return iso;
  const diffMs = now.getTime() - ms;
  if (diffMs < 0) return then.toLocaleString();
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 45) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return then.toLocaleDateString();
}
