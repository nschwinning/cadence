import { useQuery } from '@tanstack/react-query';
import { getHealth } from './client';
import type { HealthResponse } from '../types/api';

/** Typed query keys for health-related queries. */
export const healthKeys = {
  all: ['health'] as const,
};

/** React Query hook for the backend health endpoint. */
export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: healthKeys.all,
    queryFn: getHealth,
  });
}
