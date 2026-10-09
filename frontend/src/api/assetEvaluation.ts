import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { AssetUniverseEvaluationResponse } from '../types/api';

/** Typed query key for the universe-evaluation query. */
export const assetEvaluationKeys = {
  evaluation: ['assets', 'universe-evaluation'] as const,
};

/**
 * Fetch the current universe evaluation. The backend lazy-fills on first read
 * when the universe is non-empty and no evaluation exists yet, so this may run
 * the AI provider and take a few seconds on a cold universe. Resolves to an
 * envelope whose `evaluation` is `null` when the universe is empty. Rejects with
 * the axios error (502 when the provider is unavailable) so callers can surface a
 * specific message.
 */
export async function getEvaluation(): Promise<AssetUniverseEvaluationResponse> {
  const { data } = await apiClient.get<AssetUniverseEvaluationResponse>(
    '/api/v1/assets/universe-evaluation',
  );
  return data;
}

/**
 * Regenerate and replace the universe evaluation on demand. Resolves to the new
 * evaluation (or a `null` envelope for an empty universe); rejects with the axios
 * error (502 when the provider is unavailable).
 */
export async function refreshEvaluation(): Promise<AssetUniverseEvaluationResponse> {
  const { data } = await apiClient.post<AssetUniverseEvaluationResponse>(
    '/api/v1/assets/universe-evaluation/refresh',
  );
  return data;
}

/**
 * React Query hook fetching the current universe evaluation. Because the GET
 * lazy-generates when empty, the first load against a fresh universe reports
 * `isLoading` while the AI provider runs.
 */
export function useAssetUniverseEvaluation() {
  return useQuery<AssetUniverseEvaluationResponse>({
    queryKey: assetEvaluationKeys.evaluation,
    queryFn: getEvaluation,
  });
}

/**
 * Mutation regenerating the universe evaluation; seeds the query cache with the
 * fresh result on success so the panel updates without a refetch.
 */
export function useRefreshAssetUniverseEvaluation() {
  const queryClient = useQueryClient();
  return useMutation<AssetUniverseEvaluationResponse, unknown, void>({
    mutationFn: refreshEvaluation,
    onSuccess: (data) => {
      queryClient.setQueryData(assetEvaluationKeys.evaluation, data);
    },
  });
}
