import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  AssetIndicatorResponse,
  TechnicalIndicatorConfig,
  WatchlistIndicatorsResponse,
} from '../types/api';

/** Typed query keys for technical-indicator queries. */
export const technicalIndicatorKeys = {
  all: ['technical-indicators'] as const,
  config: ['technical-indicators', 'config'] as const,
  watchlist: ['technical-indicators', 'watchlist'] as const,
  asset: (ticker: string) =>
    ['technical-indicators', 'asset', ticker] as const,
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

/**
 * Fetch the short-window technical profile for every watchlist asset in one
 * batched call (one item per watchlist asset, each flagged with
 * `insufficient_history`), plus the minimum-bars floor used to derive it.
 */
export async function getWatchlistIndicators(): Promise<WatchlistIndicatorsResponse> {
  const { data } = await apiClient.get<WatchlistIndicatorsResponse>(
    '/api/v1/technical-indicators/watchlist',
  );
  return data;
}

/** React Query hook for the batched watchlist technical-indicators endpoint. */
export function useWatchlistIndicators() {
  return useQuery<WatchlistIndicatorsResponse>({
    queryKey: technicalIndicatorKeys.watchlist,
    queryFn: getWatchlistIndicators,
  });
}

/**
 * Fetch the short-window technical profile for a single asset of any membership
 * (universe or watchlist). Returns the min-bars floor and the projected
 * indicator snapshot (flagged `insufficient_history` when there is no computed
 * snapshot or too little history), or rejects 404 for an unknown ticker.
 */
export async function getAssetIndicators(
  ticker: string,
): Promise<AssetIndicatorResponse> {
  const { data } = await apiClient.get<AssetIndicatorResponse>(
    `/api/v1/technical-indicators/assets/${encodeURIComponent(ticker)}`,
  );
  return data;
}

/** React Query hook for a single asset's short-window technical profile. */
export function useAssetIndicators(ticker: string) {
  return useQuery<AssetIndicatorResponse>({
    queryKey: technicalIndicatorKeys.asset(ticker),
    queryFn: () => getAssetIndicators(ticker),
    enabled: ticker.length > 0,
  });
}
