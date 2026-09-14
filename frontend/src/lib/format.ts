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
