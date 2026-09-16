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
