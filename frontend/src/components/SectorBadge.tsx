import type { Sector } from '../types/api';

/** Display label + subtle badge colors per economic sector. */
export const SECTOR_STYLES: Record<
  Sector,
  { label: string; className: string }
> = {
  technology: { label: 'Technology', className: 'bg-indigo-100 text-indigo-800' },
  'financial-services': {
    label: 'Financial Services',
    className: 'bg-emerald-100 text-emerald-800',
  },
  healthcare: { label: 'Healthcare', className: 'bg-rose-100 text-rose-800' },
  'consumer-cyclical': {
    label: 'Consumer Cyclical',
    className: 'bg-orange-100 text-orange-800',
  },
  'consumer-defensive': {
    label: 'Consumer Defensive',
    className: 'bg-lime-100 text-lime-800',
  },
  industrials: { label: 'Industrials', className: 'bg-slate-100 text-slate-700' },
  energy: { label: 'Energy', className: 'bg-amber-100 text-amber-800' },
  'basic-materials': {
    label: 'Basic Materials',
    className: 'bg-yellow-100 text-yellow-800',
  },
  'real-estate': { label: 'Real Estate', className: 'bg-teal-100 text-teal-800' },
  utilities: { label: 'Utilities', className: 'bg-cyan-100 text-cyan-800' },
  'communication-services': {
    label: 'Communication Services',
    className: 'bg-fuchsia-100 text-fuchsia-800',
  },
};

/**
 * A small rounded pill labelling an asset's economic sector. `null` renders an
 * explicit muted "No sector" affordance rather than a blank cell.
 */
export function SectorBadge({ sector }: { sector: Sector | null }) {
  if (sector === null) {
    return (
      <span
        className="inline-flex items-center rounded-full bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-400"
        title="No sector reported by the market-data provider"
      >
        No sector
      </span>
    );
  }
  const { label, className } = SECTOR_STYLES[sector];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}
    >
      {label}
    </span>
  );
}

export default SectorBadge;
