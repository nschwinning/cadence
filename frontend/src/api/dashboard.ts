import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { DashboardMetrics } from '../types/api';

/** Typed query keys for dashboard-related queries. */
export const dashboardKeys = {
  all: ['dashboard'] as const,
  metrics: ['dashboard', 'metrics'] as const,
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
