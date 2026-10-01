/** Shared test fixtures for the dashboard overview components. */

import type {
  DashboardOverview,
  DashboardSessionPerformance,
} from '../../types/api';

/** Build a session performance row with sensible defaults. */
export function makeSession(
  overrides: Partial<DashboardSessionPerformance> = {},
): DashboardSessionPerformance {
  return {
    id: 'session-a',
    label: 'Portfolio A',
    allocated_capital: 10000,
    current_value: 11000,
    pnl: 1000,
    fees: 2,
    points: [
      { date: '2026-06-01', value: 10000 },
      { date: '2026-06-15', value: 11000 },
    ],
    ...overrides,
  };
}

/** Build a full overview payload with sensible defaults. */
export function makeOverview(
  overrides: Partial<DashboardOverview> = {},
): DashboardOverview {
  return {
    range: '1M',
    sessions: [makeSession()],
    automation: {
      latest_run: {
        id: 'run-1',
        event_type: 'REBALANCE',
        status: 'COMPLETED',
        created_at: '2026-06-15T13:40:00Z',
        session_id: 'session-a',
      },
      in_flight: false,
      failed_in_range: 0,
      next_run_approx: '2026-06-16T13:35:00Z',
      next_run_is_approximate: true,
    },
    recent_activity: [
      {
        id: 'run-1',
        session_id: 'session-a',
        session_label: 'Portfolio A',
        kind: 'REBALANCE',
        status: 'COMPLETED',
        created_at: '2026-06-15T13:40:00Z',
      },
    ],
    universe_balance: {
      total: 120,
      eligible: 90,
      ineligible: 30,
      sectors_count: 8,
      top_sector_key: 'technology',
      top_sector_share: 0.25,
      top_category_key: 'stock',
      top_category_share: 0.6,
    },
    universe_performers: {
      best: [
        { asset_id: 1, ticker: 'TECH', name: 'Tech Co', return_pct: 0.2 },
      ],
      worst: [
        { asset_id: 2, ticker: 'FIN', name: 'Fin Co', return_pct: -0.1 },
      ],
    },
    ...overrides,
  };
}
