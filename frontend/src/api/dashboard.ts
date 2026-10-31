import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  DashboardAiCosts,
  DashboardMetrics,
  DashboardOverview,
  DashboardRange,
} from '../types/api';

/** Typed query keys for dashboard-related queries. */
export const dashboardKeys = {
  all: ['dashboard'] as const,
  metrics: ['dashboard', 'metrics'] as const,
  overview: (range: DashboardRange) =>
    ['dashboard', 'overview', range] as const,
  aiCosts: ['dashboard', 'ai-costs'] as const,
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
    // Keep the previous range's data on screen while the next range loads, so
    // switching ranges swaps just the figures instead of unmounting the page
    // into a full-screen loading state. `isPlaceholderData` flags the interim.
    placeholderData: keepPreviousData,
    // Live-refresh the marked-to-market overview ~every 30s. Pauses in the
    // background (TanStack default refetchIntervalInBackground: false).
    refetchInterval: 30_000,
  });
}

/**
 * Fetch the per-portfolio AI cost breakdown. All-time and range-independent, so
 * it is a separate fetch from the range-scoped overview.
 */
export async function getDashboardAiCosts(): Promise<DashboardAiCosts> {
  const { data } = await apiClient.get<DashboardAiCosts>(
    '/api/v1/dashboard/ai-costs',
  );
  return data;
}

/** React Query hook for the per-portfolio AI cost breakdown. */
export function useDashboardAiCosts() {
  return useQuery<DashboardAiCosts>({
    queryKey: dashboardKeys.aiCosts,
    queryFn: getDashboardAiCosts,
    // Refresh ~every 30s to match the overview's live cadence.
    refetchInterval: 30_000,
  });
}
