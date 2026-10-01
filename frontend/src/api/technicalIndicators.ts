import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { TechnicalIndicatorConfig } from '../types/api';

/** Typed query keys for technical-indicator queries. */
export const technicalIndicatorKeys = {
  all: ['technical-indicators'] as const,
  config: ['technical-indicators', 'config'] as const,
};

/** Fetch the read-only technical-indicator configuration. */
export async function getTechnicalIndicatorConfig(): Promise<TechnicalIndicatorConfig> {
  const { data } = await apiClient.get<TechnicalIndicatorConfig>(
    '/api/v1/technical-indicators/config',
  );
  return data;
}

/** React Query hook for the technical-indicator config endpoint. */
export function useTechnicalIndicatorConfig() {
  return useQuery<TechnicalIndicatorConfig>({
    queryKey: technicalIndicatorKeys.config,
    queryFn: getTechnicalIndicatorConfig,
  });
}
