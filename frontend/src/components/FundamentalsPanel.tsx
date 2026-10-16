import type { AssetFundamentals, FundamentalsFigure } from '../types/api';

/** Order + labels for the known EDGAR figures we render. */
const FIGURE_ROWS: { key: string; label: string; marginOf?: 'revenue' }[] = [
  { key: 'revenue', label: 'Revenue' },
  { key: 'gross_profit', label: 'Gross profit', marginOf: 'revenue' },
  { key: 'operating_income', label: 'Operating income', marginOf: 'revenue' },
  { key: 'net_income', label: 'Net income', marginOf: 'revenue' },
  { key: 'operating_cash_flow', label: 'Operating cash flow' },
  { key: 'eps_basic', label: 'EPS (basic)' },
  { key: 'eps_diluted', label: 'EPS (diluted)' },
];

/** Keys rendered as per-share currency rather than compact large numbers. */
const PER_SHARE_KEYS = new Set(['eps_basic', 'eps_diluted']);

/** Format a large USD figure compactly (e.g. `$1.2B`, `-$340.0M`). */
function formatCompactUsd(value: number): string {
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  const units: [number, string][] = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'K'],
  ];
  for (const [scale, suffix] of units) {
    if (abs >= scale) return `${sign}$${(abs / scale).toFixed(1)}${suffix}`;
  }
  return `${sign}$${abs.toFixed(0)}`;
}

/** Format a per-share figure (EPS) with two decimals. */
function formatPerShare(value: number): string {
  const sign = value < 0 ? '-' : '';
  return `${sign}$${Math.abs(value).toFixed(2)}`;
}

/** Format a single figure's value for display, by key. */
function formatFigureValue(key: string, figure: FundamentalsFigure): string {
  return PER_SHARE_KEYS.has(key)
    ? formatPerShare(figure.value)
    : formatCompactUsd(figure.value);
}

/** A readable company-details value, flattening arrays/objects to text. */
function detailText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) {
    const joined = value.filter((v) => v != null).join(', ');
    return joined.length > 0 ? joined : null;
  }
  if (typeof value === 'object') return null;
  const text = String(value);
  return text.length > 0 ? text : null;
}

/** The company details worth surfacing, in display order (label → doc key). */
const DETAIL_ROWS: { key: string; label: string }[] = [
  { key: 'sicDescription', label: 'Industry' },
  { key: 'exchanges', label: 'Exchanges' },
  { key: 'sic', label: 'SIC code' },
];

/**
 * The fundamentals detail block for one asset, of any membership. Renders a
 * "no fundamentals on record" note when `fundamentals` is `null`, the unavailable
 * note when the row exists but EDGAR had nothing, otherwise the figures table
 * plus company details.
 */
export function FundamentalsPanel({
  fundamentals,
}: {
  fundamentals: AssetFundamentals | null;
}) {
  if (fundamentals === null) {
    return (
      <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
        No fundamentals on record for this asset.
      </p>
    );
  }

  if (fundamentals.status === 'unavailable') {
    return (
      <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
        Fundamentals unavailable — SEC EDGAR had no filings for this ticker or was
        unreachable when it was added.
      </p>
    );
  }

  const figures = fundamentals.document.figures ?? {};
  const revenue = figures.revenue?.value;
  const rows = FIGURE_ROWS.filter((row) => figures[row.key] !== undefined);
  const details = (fundamentals.document.company_details ?? {}) as Record<
    string,
    unknown
  >;
  const detailRows = DETAIL_ROWS.map((row) => ({
    label: row.label,
    text: detailText(details[row.key]),
  })).filter((row) => row.text !== null);

  return (
    <div className="flex flex-col gap-3">
      {fundamentals.status === 'partial' && (
        <p className="text-xs font-medium text-amber-700">
          Partial fundamentals — some figures were missing from EDGAR.
        </p>
      )}

      {rows.length > 0 ? (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <th className="py-1 pr-4">Figure</th>
              <th className="py-1 pr-4 text-right">Latest annual</th>
              <th className="py-1 text-right">Margin</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const figure = figures[row.key]!;
              const margin =
                row.marginOf === 'revenue' &&
                typeof revenue === 'number' &&
                revenue !== 0
                  ? (figure.value / revenue) * 100
                  : null;
              return (
                <tr key={row.key} className="border-t border-slate-100">
                  <td className="py-1 pr-4 text-slate-700">{row.label}</td>
                  <td className="py-1 pr-4 text-right font-medium tabular-nums text-slate-900">
                    {formatFigureValue(row.key, figure)}
                    {figure.period_end && (
                      <span className="ml-1 text-xs font-normal text-slate-400">
                        ({figure.period_end})
                      </span>
                    )}
                  </td>
                  <td className="py-1 text-right tabular-nums text-slate-600">
                    {margin !== null ? `${margin.toFixed(1)}%` : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-slate-500">
          No figures were reported for this company.
        </p>
      )}

      {detailRows.length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
          {detailRows.map((row) => (
            <div key={row.label} className="contents">
              <dt className="text-slate-500">{row.label}</dt>
              <dd className="text-slate-700">{row.text}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

export default FundamentalsPanel;
