import { DASHBOARD_RANGES } from '../../types/api';
import type { DashboardRange } from '../../types/api';

/**
 * Broker-style segmented range selector pinned at the top of the dashboard. A
 * single range is active at a time; changing it drives the dashboard-level range
 * state, which re-keys the overview query. Styled like the comparison chart's
 * metric toggle for visual consistency.
 */
export function RangeSelector({
  value,
  onChange,
}: {
  value: DashboardRange;
  onChange: (range: DashboardRange) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Date range"
      className="inline-flex overflow-hidden rounded border border-slate-300 text-sm"
    >
      {DASHBOARD_RANGES.map((range, i) => (
        <button
          key={range}
          type="button"
          aria-pressed={value === range}
          onClick={() => onChange(range)}
          className={`px-3 py-1 font-medium ${
            i > 0 ? 'border-l border-slate-300' : ''
          } ${
            value === range
              ? 'bg-emerald-600 text-white'
              : 'bg-white text-slate-700 hover:bg-slate-50'
          }`}
        >
          {range}
        </button>
      ))}
    </div>
  );
}

export default RangeSelector;
