import type { AssetCategory } from '../types/api';

/** Display label + subtle badge colors per asset category. */
export const CATEGORY_STYLES: Record<
  AssetCategory,
  { label: string; className: string }
> = {
  stock: { label: 'Stock', className: 'bg-sky-100 text-sky-800' },
  crypto: { label: 'Crypto', className: 'bg-amber-100 text-amber-800' },
  etf: { label: 'ETF', className: 'bg-violet-100 text-violet-800' },
  fund: { label: 'Fund', className: 'bg-teal-100 text-teal-800' },
  other: { label: 'Other', className: 'bg-slate-100 text-slate-700' },
};

/** A small rounded pill labelling an asset's instrument category. */
export function CategoryBadge({ category }: { category: AssetCategory }) {
  const { label, className } = CATEGORY_STYLES[category];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}
    >
      {label}
    </span>
  );
}

export default CategoryBadge;
