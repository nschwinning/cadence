import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  BenchmarkCatalogEntry,
  ClosedPositionListResponse,
  PaperTradeListResponse,
  PaperTradeReconcileResult,
  PaperTradingSession,
  PaperTradingSessionKpis,
  PaperTradingSessionListResponse,
  SessionRunListResponse,
  SessionStatus,
  SessionValueHistoryResponse,
} from '../types/api';

/** How often the order-sync poll re-reconciles while a trade is still open. */
const POLL_INTERVAL_MS = 1500;

/** Order statuses that will never change again (mirrors the backend terminal set). */
const TERMINAL_ORDER_STATUSES = new Set(['filled', 'cancelled', 'rejected']);

/** Whether an order status is terminal, so reconciliation can stop polling. */
export function isTerminalOrderStatus(status: string): boolean {
  return TERMINAL_ORDER_STATUSES.has(status);
}

/** Parameters that identify a paper-trading sessions list query. */
export interface SessionsListParams {
  status?: SessionStatus;
  includeArchived?: boolean;
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
  valueHistory: (sessionId: string) =>
    ['paper-trading', 'session', sessionId, 'value-history'] as const,
  kpis: (sessionId: string) =>
    ['paper-trading', 'session', sessionId, 'kpis'] as const,
  orderSync: (sessionId: string) =>
    ['paper-trading', 'session', sessionId, 'order-sync'] as const,
  benchmarks: () => ['paper-trading', 'benchmarks'] as const,
};

/** Fetch paper-trading sessions (most recently updated first) plus the total. */
export async function listSessions(
  params: SessionsListParams = DEFAULT_SESSIONS_PARAMS,
): Promise<PaperTradingSessionListResponse> {
  const query: Record<string, string | number | boolean> = {
    limit: params.limit,
  };
  if (params.status) query.status = params.status;
  if (params.includeArchived) query.include_archived = true;
  const { data } = await apiClient.get<PaperTradingSessionListResponse>(
    '/api/v1/paper-trading/sessions',
    { params: query },
  );
  return data;
}

/** Archive a stopped session. Rejects with the axios error (404/409). */
export async function archiveSession(
  sessionId: string,
): Promise<PaperTradingSession> {
  const { data } = await apiClient.post<PaperTradingSession>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/archive`,
    {},
  );
  return data;
}

/** Restore an archived session. Rejects with the axios error (404). */
export async function unarchiveSession(
  sessionId: string,
): Promise<PaperTradingSession> {
  const { data } = await apiClient.post<PaperTradingSession>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/unarchive`,
    {},
  );
  return data;
}

/** Reconcile a session's non-terminal orders; returns counts + refreshed trades. */
export async function reconcileSession(
  sessionId: string,
): Promise<PaperTradeReconcileResult> {
  const { data } = await apiClient.post<PaperTradeReconcileResult>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/reconcile`,
    {},
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

/** Fetch a session's daily value snapshots, oldest date first. */
export async function listSessionValueHistory(
  sessionId: string,
): Promise<SessionValueHistoryResponse> {
  const { data } = await apiClient.get<SessionValueHistoryResponse>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/value-history`,
  );
  return data;
}

/** Fetch a session's live performance KPIs (value marked to market on load). */
export async function getSessionKpis(
  sessionId: string,
): Promise<PaperTradingSessionKpis> {
  const { data } = await apiClient.get<PaperTradingSessionKpis>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/kpis`,
  );
  return data;
}

/** Fetch the fixed benchmark catalog (`[{id, name}]`). */
export async function listBenchmarks(): Promise<BenchmarkCatalogEntry[]> {
  const { data } = await apiClient.get<BenchmarkCatalogEntry[]>(
    '/api/v1/paper-trading/benchmarks',
  );
  return data;
}

/** Switch a session's benchmark; returns the updated session. */
export async function changeSessionBenchmark(
  sessionId: string,
  benchmark: string,
): Promise<PaperTradingSession> {
  const { data } = await apiClient.put<PaperTradingSession>(
    `/api/v1/paper-trading/sessions/${encodeURIComponent(sessionId)}/benchmark`,
    { benchmark },
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

/** React Query hook fetching a session's daily value history. */
export function useSessionValueHistory(sessionId: string) {
  return useQuery<SessionValueHistoryResponse>({
    queryKey: paperTradingKeys.valueHistory(sessionId),
    queryFn: () => listSessionValueHistory(sessionId),
    enabled: sessionId.length > 0,
  });
}

/** React Query hook fetching a session's live performance KPIs. */
export function useSessionKpis(sessionId: string) {
  return useQuery<PaperTradingSessionKpis>({
    queryKey: paperTradingKeys.kpis(sessionId),
    queryFn: () => getSessionKpis(sessionId),
    enabled: sessionId.length > 0,
  });
}

/** React Query hook fetching the fixed benchmark catalog. */
export function useBenchmarks() {
  return useQuery<BenchmarkCatalogEntry[]>({
    queryKey: paperTradingKeys.benchmarks(),
    queryFn: () => listBenchmarks(),
  });
}

/**
 * Mutation switching a session's benchmark. On success it invalidates the
 * session's own query, its KPIs, and its value-history so the benchmark figures
 * (return, excess return, chart overlay) refresh against the new series.
 */
export function useChangeSessionBenchmark(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation<PaperTradingSession, unknown, string>({
    mutationFn: (benchmark: string) =>
      changeSessionBenchmark(sessionId, benchmark),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: paperTradingKeys.all });
      queryClient.invalidateQueries({
        queryKey: paperTradingKeys.kpis(sessionId),
      });
      queryClient.invalidateQueries({
        queryKey: paperTradingKeys.valueHistory(sessionId),
      });
    },
  });
}

/**
 * Reconcile a session's orders on mount, then poll every {@link POLL_INTERVAL_MS}
 * until every returned trade reaches a terminal status. Each reconcile that
 * updates at least one trade invalidates the session's trades, positions, and
 * value-history queries so their panels reflect the new fills. Disabled while
 * `sessionId` is empty.
 */
export function useSessionOrderSync(sessionId: string) {
  const queryClient = useQueryClient();
  const query = useQuery<PaperTradeReconcileResult>({
    queryKey: paperTradingKeys.orderSync(sessionId),
    queryFn: () => reconcileSession(sessionId),
    enabled: sessionId.length > 0,
    refetchInterval: (q) => {
      const trades = q.state.data?.trades;
      if (trades === undefined) return POLL_INTERVAL_MS;
      const anyOpen = trades.some(
        (trade) => !isTerminalOrderStatus(trade.order_status),
      );
      return anyOpen ? POLL_INTERVAL_MS : false;
    },
  });

  const reconciled = query.data?.trades_reconciled;
  const updatedAt = query.dataUpdatedAt;
  useEffect(() => {
    if (!reconciled) return;
    queryClient.invalidateQueries({
      queryKey: paperTradingKeys.trades(sessionId),
    });
    queryClient.invalidateQueries({
      queryKey: paperTradingKeys.positions(sessionId),
    });
    queryClient.invalidateQueries({
      queryKey: paperTradingKeys.valueHistory(sessionId),
    });
  }, [reconciled, updatedAt, queryClient, sessionId]);

  return query;
}

/** Mutation archiving a session; invalidates the sessions list on success. */
export function useArchiveSession() {
  const queryClient = useQueryClient();
  return useMutation<PaperTradingSession, unknown, string>({
    mutationFn: (sessionId: string) => archiveSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: paperTradingKeys.all });
    },
  });
}

/** Mutation unarchiving a session; invalidates the sessions list on success. */
export function useUnarchiveSession() {
  const queryClient = useQueryClient();
  return useMutation<PaperTradingSession, unknown, string>({
    mutationFn: (sessionId: string) => unarchiveSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: paperTradingKeys.all });
    },
  });
}
