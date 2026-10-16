import type { WatchlistIndicator } from '../types/api';

/** Format a (possibly large, possibly negative) count compactly, e.g. `1.2M`. */
function formatCompactNumber(value: number): string {
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  const units: [number, string][] = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'K'],
  ];
  for (const [scale, suffix] of units) {
    if (abs >= scale) return `${sign}${(abs / scale).toFixed(1)}${suffix}`;
  }
  return `${sign}${abs.toFixed(0)}`;
}

/**
 * The short-window technical indicators we surface for an asset, in display
 * order. Each formats its (already non-null) value for the table.
 */
const INDICATOR_ROWS: {
  key: keyof WatchlistIndicator;
  label: string;
  format: (value: number) => string;
}[] = [
  { key: 'rsi_14', label: 'RSI (14)', format: (v) => v.toFixed(1) },
  { key: 'macd_line', label: 'MACD line', format: (v) => v.toFixed(2) },
  { key: 'macd_signal', label: 'MACD signal', format: (v) => v.toFixed(2) },
  { key: 'macd_hist', label: 'MACD histogram', format: (v) => v.toFixed(2) },
  { key: 'ema_20', label: 'EMA (20)', format: (v) => `$${v.toFixed(2)}` },
  { key: 'bb_pctb', label: 'Bollinger %b', format: (v) => v.toFixed(2) },
  {
    key: 'bb_width',
    label: 'Bollinger bandwidth',
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: 'hvol_20',
    label: 'Hist. volatility (20)',
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: 'vol_ratio_50',
    label: 'Volume vs 50-day avg',
    format: (v) => `${v.toFixed(2)}×`,
  },
  {
    key: 'obv_change_20d',
    label: 'OBV 20-day change',
    format: (v) => formatCompactNumber(v),
  },
];

/** The short-window reversal flags, labelled for the "active flags" chips. */
const REVERSAL_FLAG_ROWS: { key: keyof WatchlistIndicator; label: string }[] = [
  { key: 'rev_macd_hist_rollover', label: 'MACD histogram rollover' },
  { key: 'rev_rsi_rollover', label: 'RSI rollover' },
  { key: 'rev_return_decel', label: 'Return deceleration' },
  { key: 'rev_obv_price_divergence', label: 'OBV / price divergence' },
];

/**
 * The short-window technical-indicator block for one asset, of any membership.
 * Renders a "no technical indicators on record" note when `indicator` is `null`,
 * the insufficient-history state below the bar floor, otherwise the values table
 * plus active reversal chips and the "as of" date.
 */
export function TechnicalPanel({
  indicator,
  minBars,
}: {
  indicator: WatchlistIndicator | null;
  minBars: number;
}) {
  if (indicator === null) {
    return (
      <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
        No technical indicators on record for this asset yet.
      </p>
    );
  }

  if (indicator.insufficient_history) {
    const have =
      indicator.bar_count !== null ? ` (have ${indicator.bar_count})` : '';
    return (
      <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
        Insufficient history for technical indicators — needs ≥ {minBars} daily
        bars{have}. They will appear once enough price history accumulates.
      </p>
    );
  }

  const rows = INDICATOR_ROWS.map((row) => ({
    label: row.label,
    value: indicator[row.key],
    format: row.format,
  })).filter(
    (row): row is typeof row & { value: number } =>
      typeof row.value === 'number',
  );

  const activeFlags = REVERSAL_FLAG_ROWS.filter((row) => indicator[row.key]);

  return (
    <div className="flex flex-col gap-3">
      {rows.length > 0 ? (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <th className="py-1 pr-4">Indicator</th>
              <th className="py-1 text-right">Latest</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-t border-slate-100">
                <td className="py-1 pr-4 text-slate-700">{row.label}</td>
                <td className="py-1 text-right font-medium tabular-nums text-slate-900">
                  {row.format(row.value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-slate-500">
          No technical indicators were computed for this asset.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Reversal flags
        </span>
        {activeFlags.length > 0 ? (
          activeFlags.map((flag) => (
            <span
              key={flag.key}
              className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800"
            >
              {flag.label}
            </span>
          ))
        ) : (
          <span className="text-xs text-slate-500">None active</span>
        )}
      </div>

      {indicator.trading_date && (
        <p className="text-xs text-slate-400">As of {indicator.trading_date}</p>
      )}
    </div>
  );
}

export default TechnicalPanel;
