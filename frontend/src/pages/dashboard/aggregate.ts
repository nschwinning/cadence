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
  /** Range realised P&L summed across the selected sessions (simple dollar sum). */
  realisedPnl: number;
  /** Range unrealised P&L summed across the selected sessions (simple dollar sum). */
  unrealisedPnl: number;
  /** Money-weighted return fraction: `Σ pnl ÷ Σ value_start` (0 when no basis). */
  returnPct: number;
  fees: number;
}

/**
 * Money-weighted aggregation over the given sessions. `returnPct` is the summed
 * P&L over the summed starting value, so larger portfolios carry proportionally
 * more weight; it falls back to 0 when no session has a positive basis. The
 * range `realisedPnl`/`unrealisedPnl` partners of the value are simple dollar
 * sums (each is already range-relative per session).
 */
export function aggregateTotals(
  sessions: DashboardSessionPerformance[],
): AggregateTotals {
  let totalValue = 0;
  let pnl = 0;
  let realisedPnl = 0;
  let unrealisedPnl = 0;
  let fees = 0;
  let basis = 0;
  for (const s of sessions) {
    totalValue += s.current_value;
    pnl += s.pnl;
    realisedPnl += s.realised_pnl;
    unrealisedPnl += s.unrealised_pnl;
    fees += s.fees;
    const start = sessionValueStart(s);
    if (start > 0) basis += start;
  }
  return {
    totalValue,
    pnl,
    realisedPnl,
    unrealisedPnl,
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
 * The index's last close on/before `date` (carry-forward over non-trading days),
 * or `null` when `date` precedes every stored close. `points` are ascending by
 * date.
 */
export function closeOnOrBefore(
  points: DashboardBenchmarkPricePoint[],
  date: string,
): number | null {
  let close: number | null = null;
  for (const p of points) {
    if (p.date <= date) close = p.price;
    else break;
  }
  return close;
}

/**
 * Build one benchmark index's dollar comparison line by aggregating a buy-and-hold
 * of the selected sessions' contributed capital in that index.
 *
 * Each contribution (a session's opening capital on its start date, or a later
 * capital increase) buys `amount / close(effective_date)` units of the index at
 * its effective date and holds. The line's value on date `t` is
 * `close(t) × Σ units bought on/before t` across all selected sessions — which is
 * exactly the sum of the per-session contribution-aware overlays. It therefore sits
 * at zero before the first selected session opens and steps up as each session
 * opens (and on each later capital increase), mirroring `combinedSeries` so the two
 * lines are directly comparable in USD.
 *
 * `points` are the index's raw closes (ascending). `dateAxis` is the shared axis
 * of the combined equity curve (the selected sessions' union of dates). A
 * contribution whose effective date precedes the index's first stored close buys
 * no units (it cannot be priced); when no contribution can be priced the line is
 * empty so the chart draws nothing.
 */
export function benchmarkDollarSeries(
  sessions: DashboardSessionPerformance[],
  points: DashboardBenchmarkPricePoint[],
  dateAxis: string[],
): CombinedPoint[] {
  if (points.length === 0 || dateAxis.length === 0) return [];

  // Units purchased per contribution at its effective date's close. A contribution
  // with no priceable close (before the index's first stored close) buys nothing.
  const purchases: { date: string; units: number }[] = [];
  for (const s of sessions) {
    for (const c of s.contributions) {
      const close = closeOnOrBefore(points, c.effective_date);
      if (close === null || close <= 0) continue;
      purchases.push({ date: c.effective_date, units: c.amount / close });
    }
  }
  if (purchases.length === 0) return [];

  return dateAxis.map((date) => {
    const close = closeOnOrBefore(points, date);
    if (close === null) return { date, value: 0 };
    let units = 0;
    for (const p of purchases) {
      if (p.date <= date) units += p.units;
    }
    return { date, value: close * units };
  });
}
