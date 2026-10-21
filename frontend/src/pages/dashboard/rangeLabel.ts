import type { DashboardRange } from '../../types/api';

/**
 * The active-range phrase for a scope-band header, e.g. "the past month". Used in
 * the Performance band header ("over the past month") and the universe performers'
 * range chip so range-scoped figures read as range-scoped at a glance.
 */
export const RANGE_PHRASE: Record<DashboardRange, string> = {
  '1D': 'today',
  '1W': 'the past week',
  '1M': 'the past month',
  YTD: 'year to date',
  '1Y': 'the past year',
  Max: 'all time',
};

/** The "over the …" preposition reads naturally for a span but not for "today". */
export function overPhrase(range: DashboardRange): string {
  const phrase = RANGE_PHRASE[range];
  return range === '1D' ? phrase : `over ${phrase}`;
}

/**
 * A capitalised column-group label for a range, e.g. "Over the past month" (or
 * "Today" for the day range). Used as the leaderboard's spanning sub-header.
 */
export function spanLabel(range: DashboardRange): string {
  if (range === '1D') return 'Today';
  return `Over ${RANGE_PHRASE[range]}`;
}
