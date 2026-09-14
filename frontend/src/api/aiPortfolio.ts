import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import { paperTradingKeys } from './paperTrading';
import type {
  AIEventStatus,
  AIPortfolioBuildRequest,
  AIPortfolioBuildResponse,
  AIPortfolioEvent,
  AIRebalanceResponse,
} from '../types/api';

/** How often (ms) to poll an in-progress build/rebalance event. */
const POLL_INTERVAL_MS = 1500;

/**
 * Whether an AI event has reached a terminal status. Terminal events no longer
 * change, so pollers stop once this returns true. Mirrors the backend
 * `TERMINAL_STATUSES` set (`succeeded`/`partial`/`failed`/`skipped`).
 */
export function isTerminalEventStatus(status: AIEventStatus): boolean {
  return (
    status === 'succeeded' ||
    status === 'partial' ||
    status === 'failed' ||
    status === 'skipped'
  );
}

/** Typed query keys for AI-portfolio queries. */
export const aiPortfolioKeys = {
  all: ['ai-portfolio'] as const,
  buildStatus: (eventId: string) =>
    ['ai-portfolio', 'build-status', eventId] as const,
  sessionEvents: (sessionId: string) =>
    ['ai-portfolio', 'session', sessionId, 'events'] as const,
};

/**
 * Queue an AI portfolio build. Resolves to the accepted (202) event id + status;
 * rejects with the axios error (status 422 validation failure) so callers can
 * surface a specific message.
 */
export async function buildAIPortfolio(
  body: AIPortfolioBuildRequest,
): Promise<AIPortfolioBuildResponse> {
  const { data } = await apiClient.post<AIPortfolioBuildResponse>(
    '/api/v1/ai-portfolio/build',
    body,
  );
  return data;
}

/**
 * Fetch a build/rebalance event's current status by event id. Rejects with the
 * axios error (404 unknown event) so callers can surface a specific message.
 */
export async function getBuildStatus(
  eventId: string,
): Promise<AIPortfolioEvent> {
  const { data } = await apiClient.get<AIPortfolioEvent>(
    `/api/v1/ai-portfolio/build/status/${encodeURIComponent(eventId)}`,
  );
  return data;
}

/**
 * Trigger an AI rebalance for a session. Resolves to the event id + status +
 * whether it was newly started; rejects with the axios error (404 unknown / 409
 * not eligible) so callers can surface a specific message.
 */
export async function rebalanceSession(
  sessionId: string,
): Promise<AIRebalanceResponse> {
  const { data } = await apiClient.post<AIRebalanceResponse>(
    `/api/v1/ai-portfolio/sessions/${encodeURIComponent(sessionId)}/rebalance`,
    {},
  );
  return data;
}

/** Fetch a session's AI events (build + rebalances), newest first. */
export async function listSessionEvents(
  sessionId: string,
  limit = 20,
): Promise<AIPortfolioEvent[]> {
  const { data } = await apiClient.get<AIPortfolioEvent[]>(
    `/api/v1/ai-portfolio/sessions/${encodeURIComponent(sessionId)}/events`,
    { params: { limit } },
  );
  return data;
}

/** Mutation queuing an AI portfolio build. */
export function useBuildAIPortfolio() {
  return useMutation<
    AIPortfolioBuildResponse,
    unknown,
    AIPortfolioBuildRequest
  >({
    mutationFn: buildAIPortfolio,
  });
}

/** Mutation triggering a per-session AI rebalance; invalidates the events list. */
export function useRebalanceSession(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation<AIRebalanceResponse, unknown, void>({
    mutationFn: () => rebalanceSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: aiPortfolioKeys.sessionEvents(sessionId),
      });
      queryClient.invalidateQueries({
        queryKey: paperTradingKeys.all,
      });
    },
  });
}

/**
 * React Query hook fetching a build/rebalance event by id, polling every
 * {@link POLL_INTERVAL_MS} while non-terminal and stopping once it reaches a
 * terminal status. Disabled while `eventId` is null.
 */
export function useBuildStatus(eventId: string | null) {
  return useQuery<AIPortfolioEvent>({
    queryKey: aiPortfolioKeys.buildStatus(eventId ?? ''),
    queryFn: () => getBuildStatus(eventId as string),
    enabled: typeof eventId === 'string' && eventId.length > 0,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === undefined || isTerminalEventStatus(status)) {
        return false;
      }
      return POLL_INTERVAL_MS;
    },
  });
}

/** React Query hook listing a session's AI events. */
export function useSessionEvents(sessionId: string) {
  return useQuery<AIPortfolioEvent[]>({
    queryKey: aiPortfolioKeys.sessionEvents(sessionId),
    queryFn: () => listSessionEvents(sessionId),
    enabled: sessionId.length > 0,
  });
}
