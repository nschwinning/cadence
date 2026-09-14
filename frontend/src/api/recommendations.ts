import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  RecommendationRun,
  RecommendationRunCreate,
  RunPhase,
} from '../types/api';

/** Typed query keys for recommendation-run queries. */
export const recommendationKeys = {
  all: ['recommendations'] as const,
  run: (id: number) => ['recommendations', 'run', id] as const,
};

/** How often (ms) to poll an in-progress run for status/results updates. */
const POLL_INTERVAL_MS = 1500;

/**
 * Whether a run has reached a terminal phase (`completed`/`failed`). Terminal
 * runs no longer change, so the detail poller stops once this returns true.
 */
export function isTerminalPhase(status: RunPhase): boolean {
  return status === 'completed' || status === 'failed';
}

/** Fetch the recommendation-run history, newest first. */
export async function listRecommendationRuns(): Promise<RecommendationRun[]> {
  const { data } = await apiClient.get<RecommendationRun[]>(
    '/api/v1/recommendations',
  );
  return data;
}

/**
 * Fetch a single recommendation run by id. Rejects with the axios error (404
 * unknown run) so callers can surface a specific message.
 */
export async function getRecommendationRun(
  id: number,
): Promise<RecommendationRun> {
  const { data } = await apiClient.get<RecommendationRun>(
    `/api/v1/recommendations/${id}`,
  );
  return data;
}

/**
 * Start a new recommendation run. Resolves to the created run on 202; rejects
 * with the axios error (status 422 validation failure) so callers can surface a
 * specific message.
 */
export async function createRecommendationRun(
  body: RecommendationRunCreate,
): Promise<RecommendationRun> {
  const { data } = await apiClient.post<RecommendationRun>(
    '/api/v1/recommendations',
    body,
  );
  return data;
}

/** React Query hook listing the recommendation-run history (newest first). */
export function useRecommendationRuns() {
  return useQuery<RecommendationRun[]>({
    queryKey: recommendationKeys.all,
    queryFn: listRecommendationRuns,
  });
}

/** Mutation starting a recommendation run; invalidates the history on success. */
export function useCreateRecommendationRun() {
  const queryClient = useQueryClient();
  return useMutation<RecommendationRun, unknown, RecommendationRunCreate>({
    mutationFn: createRecommendationRun,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: recommendationKeys.all });
    },
  });
}

/**
 * React Query hook fetching a single run by id, polling every
 * {@link POLL_INTERVAL_MS} while the run is non-terminal and stopping (returns
 * `false`) once it reaches a terminal phase. Disabled while `id` is null.
 */
export function useRecommendationRun(id: number | null) {
  return useQuery<RecommendationRun>({
    queryKey: recommendationKeys.run(id ?? -1),
    queryFn: () => getRecommendationRun(id as number),
    enabled: typeof id === 'number',
    // v5 signature: receives the query so we can read the latest cached status
    // and stop polling as soon as the run is terminal.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === undefined || isTerminalPhase(status)) {
        return false;
      }
      return POLL_INTERVAL_MS;
    },
  });
}
