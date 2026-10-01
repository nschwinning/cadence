import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { DashboardMetrics, DashboardOverview, DashboardRange } from '../types/api';

/** Typed query keys for dashboard-related queries. */
export const dashboardKeys = {
  all: ['dashboard'] as const,
  metrics: ['dashboard', 'metrics'] as const,
  overview: (range: DashboardRange) =>
    ['dashboard', 'overview', range] as const,
};

/** Fetch the aggregate overview metrics. Resolves to the typed payload on 200. */
export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  const { data } = await apiClient.get<DashboardMetrics>(
    '/api/v1/dashboard/metrics',
  );
  return data;
}

/** React Query hook for the dashboard metrics endpoint. */
export function useDashboardMetrics() {
  return useQuery<DashboardMetrics>({
    queryKey: dashboardKeys.metrics,
    queryFn: getDashboardMetrics,
  });
}

/** Fetch the range-scoped dashboard overview. Resolves to the typed payload on 200. */
export async function getDashboardOverview(
  range: DashboardRange,
): Promise<DashboardOverview> {
  const { data } = await apiClient.get<DashboardOverview>(
    '/api/v1/dashboard/overview',
    { params: { range } },
  );
  return data;
}

/** React Query hook for the dashboard overview, keyed by the selected range. */
export function useDashboardOverview(range: DashboardRange) {
  return useQuery<DashboardOverview>({
    queryKey: dashboardKeys.overview(range),
    queryFn: () => getDashboardOverview(range),
  });
}
