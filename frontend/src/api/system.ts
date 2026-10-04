import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { SystemStatusResponse } from '../types/api';

/** Typed query keys for system-status queries. */
export const systemKeys = {
  all: ['system'] as const,
  status: ['system', 'status'] as const,
};

/** Fetch the live status of every connected external backend. */
export async function getSystemStatus(): Promise<SystemStatusResponse> {
  const { data } = await apiClient.get<SystemStatusResponse>(
    '/api/v1/system/status',
  );
  return data;
}

/**
 * React Query hook for the system-status endpoint. Polls every 30s to keep the
 * view reasonably current; callers use the returned `refetch` for manual refresh.
 */
export function useSystemStatus() {
  return useQuery<SystemStatusResponse>({
    queryKey: systemKeys.status,
    queryFn: getSystemStatus,
    refetchInterval: 30_000,
  });
}
