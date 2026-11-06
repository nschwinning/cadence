/**
 * Shared, pure last-observation-carried-forward (LOCF) helpers for the
 * paper-trading / dashboard value charts.
 *
 * The daily snapshot job deliberately skips equity-only sessions while the US
 * market is closed, so an equity-only session has no `SessionValueSnapshot` for
 * weekends. Plotting only the stored points makes such a line stop on Friday. To
 * keep the line visible and comparable, we carry each series' last recorded value
 * forward across dates it has no snapshot for (a flat segment equal to the
 * preceding trading day's value) and extend the shared axis to a trailing horizon
 * of "yesterday" (ET). These are end-of-day charts, so they never plot a point for
 * today — today's snapshot does not exist until the end-of-day job runs — but the
 * carry-forward still fills any closed-market gap up to yesterday. This is a
 * presentation-only fill — stored snapshots are untouched.
 *
 * Mirrors the pure-aggregation pattern in `pages/dashboard/aggregate.ts`.
 */

/** A dated value point. Dates are ET calendar dates (`YYYY-MM-DD`). */
export interface DatedValue {
  date: string;
  value: number;
}

/**
 * The current calendar date in `America/New_York`, formatted as `YYYY-MM-DD` so
 * it sorts and compares lexicographically against snapshot date strings. `now` is
 * injectable for deterministic tests.
 */
export function todayEt(now: Date = new Date()): string {
  // `en-CA` renders as `YYYY-MM-DD`; the ET time zone matches how snapshots are keyed.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

/**
 * The calendar date before `todayEt`, as `YYYY-MM-DD`. Used as the trailing
 * carry-forward horizon for end-of-day charts: they extend the axis only up to
 * yesterday, because today has no end-of-day snapshot yet. Computed by one-day
 * arithmetic on the ET calendar date string (via a UTC date so it is DST-safe and
 * independent of the viewer's local time zone). `now` is injectable for tests.
 */
export function yesterdayEt(now: Date = new Date()): string {
  const [year, month, day] = todayEt(now).split('-').map(Number);
  const dt = new Date(Date.UTC(year, month - 1, day));
  dt.setUTCDate(dt.getUTCDate() - 1);
  const y = dt.getUTCFullYear();
  const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const d = String(dt.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * Build the sorted, de-duplicated union date axis from one or more series' dates,
 * extended to a trailing `horizon` when the horizon falls on or after the latest
 * date (it is appended only when strictly later, so an existing date is never
 * duplicated). An empty input with a horizon yields just the horizon; an empty
 * input with no horizon yields an empty axis.
 */
export function unionDateAxis(
  seriesDates: string[][],
  horizon?: string,
): string[] {
  const set = new Set<string>();
  for (const dates of seriesDates) {
    for (const d of dates) set.add(d);
  }
  const axis = Array.from(set).sort();
  if (horizon !== undefined) {
    const last = axis[axis.length - 1];
    if (last === undefined || horizon > last) axis.push(horizon);
  }
  return axis;
}

/**
 * Map `points` onto `axis` with last-observation-carried-forward: each axis date
 * gets the value of the most recent point on or before it, or `null` for dates
 * that precede the series' first point (no backfill). `points` need not be
 * pre-sorted. Returns one entry per axis date, in axis order.
 */
export function carryForwardOnto(
  points: DatedValue[],
  axis: string[],
): (number | null)[] {
  const sorted = [...points].sort((a, b) =>
    a.date < b.date ? -1 : a.date > b.date ? 1 : 0,
  );
  const result: (number | null)[] = [];
  let i = 0;
  let carried: number | null = null;
  for (const date of axis) {
    while (i < sorted.length && sorted[i].date <= date) {
      carried = sorted[i].value;
      i += 1;
    }
    result.push(carried);
  }
  return result;
}

/**
 * Carry `points` forward onto `axis` and drop the leading dates before the
 * series' first point, so the returned series starts at its first real value and
 * then stays flat over any date with no point (interior gaps and the trailing
 * horizon). Returns `{date, value}` points in axis order.
 */
export function carryForwardSeries(
  points: DatedValue[],
  axis: string[],
): DatedValue[] {
  const values = carryForwardOnto(points, axis);
  const out: DatedValue[] = [];
  for (let k = 0; k < axis.length; k += 1) {
    const v = values[k];
    if (v === null) continue;
    out.push({ date: axis[k], value: v });
  }
  return out;
}
