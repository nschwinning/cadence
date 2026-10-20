/**
 * Pure client-side re-aggregation of the per-session overview data.
 *
 * The backend returns each active session's range-scoped performance once; the
 * dashboard then re-derives the hero tiles, leaderboard figures, and the
 * combined equity curve from whichever sessions the user has selected — no
 * refetch per toggle. All math here is money-weighted and matches the backend's
 * definitions so the aggregate tiles agree with the per-session numbers.
 */

import type {
  DashboardBenchmarkPricePoint,
  DashboardSessionPerformance,
} from '../../types/api';

/** A session's value at the range start, derived as `current_value - pnl`. */
export function sessionValueStart(session: DashboardSessionPerformance): number {
  return session.current_value - session.pnl;
}

/**
 * A session's range return as a fraction (`pnl / value_start`), or `null` when
 * the start value is non-positive and a return cannot be normalised.
 */
export function sessionReturnPct(
  session: DashboardSessionPerformance,
): number | null {
  const start = sessionValueStart(session);
  if (start <= 0) return null;
  return session.pnl / start;
}

/** The money-weighted aggregate figures for the hero tiles. */
export interface AggregateTotals {
  totalValue: number;
  pnl: number;
  /** Money-weighted return fraction: `Σ pnl ÷ Σ value_start` (0 when no basis). */
  returnPct: number;
  fees: number;
}

/**
 * Money-weighted aggregation over the given sessions. `returnPct` is the summed
 * P&L over the summed starting value, so larger portfolios carry proportionally
 * more weight; it falls back to 0 when no session has a positive basis.
 */
export function aggregateTotals(
  sessions: DashboardSessionPerformance[],
): AggregateTotals {
  let totalValue = 0;
  let pnl = 0;
  let fees = 0;
  let basis = 0;
  for (const s of sessions) {
    totalValue += s.current_value;
    pnl += s.pnl;
    fees += s.fees;
    const start = sessionValueStart(s);
    if (start > 0) basis += start;
  }
  return {
    totalValue,
    pnl,
    fees,
    returnPct: basis > 0 ? pnl / basis : 0,
  };
}

/** One point of the combined equity curve: a date and the summed value. */
export interface CombinedPoint {
  date: string;
  value: number;
}

/**
 * Sum the selected sessions onto a single value series over their shared date
 * axis. Each session's value is carried forward from its last snapshot on/before
 * a date, and contributes 0 before its first snapshot — so a newer session adds
 * nothing to earlier dates rather than dropping the whole point. Returns points
 * oldest-first; empty when nothing is selected or no session has points.
 */
export function combinedSeries(
  sessions: DashboardSessionPerformance[],
): CombinedPoint[] {
  const dates = Array.from(
    new Set(sessions.flatMap((s) => s.points.map((p) => p.date))),
  ).sort();
  return dates.map((date) => {
    let value = 0;
    for (const s of sessions) {
      let carried = 0;
      for (const p of s.points) {
        if (p.date <= date) carried = p.value;
        else break;
      }
      value += carried;
    }
    return { date, value };
  });
}

/**
 * Rebase a benchmark's raw price series onto the combined equity curve, so the
 * line answers "what the combined curve's starting capital would be worth
 * invested in that index". `points` are ascending by date and may include a
 * single pre-start anchor close (as the backend sends). `start` is the combined
 * curve's first point `{date, value}`.
 *
 * The anchor price is the index's last close on/before the combined start date;
 * the line then tracks `start.value × price(t) / anchor` for every close on/after
 * the start. When the anchor is on/before the start, the line is seeded with the
 * start point itself so it shares the portfolio line's origin. When every stored
 * close is *after* the start (no on/before anchor), the earliest close anchors the
 * line instead, so it begins at the first available date. Returns an empty line
 * when there are no points or the anchor price is non-positive.
 */
export function rebaseBenchmarkLine(
  points: DashboardBenchmarkPricePoint[],
  start: CombinedPoint,
): CombinedPoint[] {
  if (points.length === 0) return [];

  // Anchor: the last close on/before the start date (carry-forward), falling back
  // to the earliest close when every stored close is after the start.
  let anchor: number | null = null;
  for (const p of points) {
    if (p.date <= start.date) anchor = p.price;
    else break;
  }
  const anchoredOnOrBeforeStart = anchor !== null;
  if (anchor === null) anchor = points[0].price;
  if (anchor <= 0) return [];

  const line: CombinedPoint[] = [];
  // Seed the origin at the combined start so both lines share a left edge; valid
  // because the anchor is the close on/before the start (value there is start.value).
  if (anchoredOnOrBeforeStart) line.push({ date: start.date, value: start.value });
  for (const p of points) {
    if (p.date < start.date) continue; // the pre-start anchor is not plotted
    if (anchoredOnOrBeforeStart && p.date === start.date) continue; // dedupe origin
    line.push({ date: p.date, value: (start.value * p.price) / anchor });
  }
  return line;
}
