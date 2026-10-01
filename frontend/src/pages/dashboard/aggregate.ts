/**
 * Pure client-side re-aggregation of the per-session overview data.
 *
 * The backend returns each active session's range-scoped performance once; the
 * dashboard then re-derives the hero tiles, leaderboard figures, and the
 * combined equity curve from whichever sessions the user has selected — no
 * refetch per toggle. All math here is money-weighted and matches the backend's
 * definitions so the aggregate tiles agree with the per-session numbers.
 */

import type { DashboardSessionPerformance } from '../../types/api';

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
