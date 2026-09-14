import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  ClosedPositionListResponse,
  PaperTradeListResponse,
  PaperTradingSessionListResponse,
  SessionRunListResponse,
  SessionStatus,
} from '../types/api';

/** Parameters that identify a paper-trading sessions list query. */
export interface SessionsListParams {
  status?: SessionStatus;
  limit: number;
}

/** Default sessions list parameters (matches the backend defaults). */
export const DEFAULT_SESSIONS_PARAMS: SessionsListParams = { limit: 50 };

/** Typed query keys for paper-trading queries. */
export const paperTradingKeys = {
  all: ['paper-trading'] as const,
  sessions: (params: SessionsListParams) =>
    ['paper-trading', 'sessions', params] as const,
  trades: (sessionId: string) =>
    ['paper-trading', 'session', sessionId, 'trades'] as const,
  runs: (sessionId: string) =>
    ['paper-trading', 'session', sessionId, 'runs'] as const,
  positions: (sessionId: string) =>
    ['paper-trading', 'session', sessionId, 'positions'] as const,
};

/** Fetch paper-trading sessions (most recently updated first) plus the total. */
export async function listSessions(
  params: SessionsListParams = DEFAULT_SESSIONS_PARAMS,
): Promise<PaperTradingSessionListResponse> {
  const query: Record<string, string | number> = { limit: params.limit };
  if (params.status) query.status = params.status;
  const { data } = await apiClient.get<PaperTradingSessionListResponse>(
    '/api/v1/paper-trading/sessions',
    { params: query },
  );
  return data;
}

/** Fetch a session's trades, most recent first. */
export async function listSessionTrades(
  sessionId: string,
  limit = 100,
): Promise<PaperTradeListResponse> {
  const { data } = await apiClient.get<PaperTradeListResponse>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/trades`,
    { params: { limit } },
  );
  return data;
}

/** Fetch a session's run history, most recent first. */
export async function listSessionRuns(
  sessionId: string,
  limit = 50,
): Promise<SessionRunListResponse> {
  const { data } = await apiClient.get<SessionRunListResponse>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/runs`,
    { params: { limit } },
  );
  return data;
}

/** Fetch a session's closed positions, most recently exited first. */
export async function listSessionPositions(
  sessionId: string,
  limit = 100,
): Promise<ClosedPositionListResponse> {
  const { data } = await apiClient.get<ClosedPositionListResponse>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/positions`,
    { params: { limit } },
  );
  return data;
}

/** React Query hook listing paper-trading sessions. */
export function useSessions(
  params: SessionsListParams = DEFAULT_SESSIONS_PARAMS,
) {
  return useQuery<PaperTradingSessionListResponse>({
    queryKey: paperTradingKeys.sessions(params),
    queryFn: () => listSessions(params),
  });
}

/** React Query hook fetching a session's trades. */
export function useSessionTrades(sessionId: string) {
  return useQuery<PaperTradeListResponse>({
    queryKey: paperTradingKeys.trades(sessionId),
    queryFn: () => listSessionTrades(sessionId),
    enabled: sessionId.length > 0,
  });
}

/** React Query hook fetching a session's run history. */
export function useSessionRuns(sessionId: string) {
  return useQuery<SessionRunListResponse>({
    queryKey: paperTradingKeys.runs(sessionId),
    queryFn: () => listSessionRuns(sessionId),
    enabled: sessionId.length > 0,
  });
}

/** React Query hook fetching a session's closed positions. */
export function useSessionPositions(sessionId: string) {
  return useQuery<ClosedPositionListResponse>({
    queryKey: paperTradingKeys.positions(sessionId),
    queryFn: () => listSessionPositions(sessionId),
    enabled: sessionId.length > 0,
  });
}
