import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from './client';
import { dashboardKeys } from './dashboard';
import type {
  BotKpis,
  BotSession,
  BotSessionCreateRequest,
  BotSessionListResponse,
  BotStrategyCatalogEntry,
  BotTradeListResponse,
  BotValueHistoryResponse,
  BotValueResolution,
} from '../types/api';

/** Typed query keys for strategy-bot queries. */
export const botKeys = {
  all: ['bots'] as const,
  strategies: () => ['bots', 'strategies'] as const,
  sessions: (includeArchived: boolean) =>
    ['bots', 'sessions', includeArchived] as const,
  session: (sessionId: string) => ['bots', 'session', sessionId] as const,
  kpis: (sessionId: string) => ['bots', 'session', sessionId, 'kpis'] as const,
  valueHistory: (sessionId: string, resolution?: BotValueResolution) =>
    ['bots', 'session', sessionId, 'value-history', resolution ?? null] as const,
  trades: (sessionId: string, limit?: number, offset?: number) =>
    ['bots', 'session', sessionId, 'trades', limit ?? null, offset ?? null] as const,
};

/**
 * Invalidate every cache surface a bot-session change can affect: the bot
 * queries (session lists, detail, KPIs, value history, trades) and the dashboard
 * aggregates (leaderboard, combined equity curve, overview) that union bot rows.
 * A create/stop/archive touches both, so they must refresh together — otherwise
 * the dashboard stays stale until a page reload.
 */
export function invalidateBotDependents(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: botKeys.all });
  queryClient.invalidateQueries({ queryKey: dashboardKeys.all });
}

/** Fetch the registered bot strategies and their default parameter schemas. */
export async function listStrategies(): Promise<BotStrategyCatalogEntry[]> {
  const { data } = await apiClient.get<BotStrategyCatalogEntry[]>(
    '/api/v1/bots/strategies',
  );
  return data;
}

/** Fetch bot sessions (newest first) plus the total. */
export async function listBotSessions(
  includeArchived = false,
): Promise<BotSessionListResponse> {
  const { data } = await apiClient.get<BotSessionListResponse>(
    '/api/v1/bots/sessions',
    { params: includeArchived ? { include_archived: true } : {} },
  );
  return data;
}

/** Create a bot session. Rejects with the axios error (422 on domain errors). */
export async function createBotSession(
  request: BotSessionCreateRequest,
): Promise<BotSession> {
  const { data } = await apiClient.post<BotSession>(
    '/api/v1/bots/sessions',
    request,
  );
  return data;
}

/** Fetch a single bot session. Rejects with the axios error (404). */
export async function getBotSession(sessionId: string): Promise<BotSession> {
  const { data } = await apiClient.get<BotSession>(
    `/api/v1/bots/sessions/${encodeURIComponent(sessionId)}`,
  );
  return data;
}

/** Stop an active bot session. Rejects with the axios error (404). */
export async function stopBotSession(sessionId: string): Promise<BotSession> {
  const { data } = await apiClient.post<BotSession>(
    `/api/v1/bots/sessions/${encodeURIComponent(sessionId)}/stop`,
    {},
  );
  return data;
}

/** Archive a stopped bot session. Rejects with the axios error (404/409). */
export async function archiveBotSession(sessionId: string): Promise<BotSession> {
  const { data } = await apiClient.post<BotSession>(
    `/api/v1/bots/sessions/${encodeURIComponent(sessionId)}/archive`,
    {},
  );
  return data;
}

/** Fetch a bot session's live performance KPIs. Rejects with the axios error (404). */
export async function getBotKpis(sessionId: string): Promise<BotKpis> {
  const { data } = await apiClient.get<BotKpis>(
    `/api/v1/bots/sessions/${encodeURIComponent(sessionId)}/kpis`,
  );
  return data;
}

/**
 * Fetch a bot session's value history at the given resolution, oldest first.
 * `resolution` defaults to `daily` (the server default) when omitted.
 */
export async function getBotValueHistory(
  sessionId: string,
  resolution?: BotValueResolution,
): Promise<BotValueHistoryResponse> {
  const { data } = await apiClient.get<BotValueHistoryResponse>(
    `/api/v1/bots/sessions/${encodeURIComponent(sessionId)}/value-history`,
    resolution ? { params: { resolution } } : undefined,
  );
  return data;
}

/** Fetch a bot session's trade ledger, most recent first. */
export async function listBotTrades(
  sessionId: string,
  { limit = 100, offset = 0 }: { limit?: number; offset?: number } = {},
): Promise<BotTradeListResponse> {
  const { data } = await apiClient.get<BotTradeListResponse>(
    `/api/v1/bots/sessions/${encodeURIComponent(sessionId)}/trades`,
    { params: { limit, offset } },
  );
  return data;
}

/** React Query hook fetching the registered bot strategy catalog. */
export function useStrategies() {
  return useQuery<BotStrategyCatalogEntry[]>({
    queryKey: botKeys.strategies(),
    queryFn: () => listStrategies(),
  });
}

/** React Query hook listing bot sessions. */
export function useBotSessions(includeArchived = false) {
  return useQuery<BotSessionListResponse>({
    queryKey: botKeys.sessions(includeArchived),
    queryFn: () => listBotSessions(includeArchived),
    // Live-refresh the marked-to-market totals ~every 30s. Pauses in the
    // background (TanStack default refetchIntervalInBackground: false).
    refetchInterval: 30_000,
  });
}

/** React Query hook fetching a single bot session. */
export function useBotSession(sessionId: string) {
  return useQuery<BotSession>({
    queryKey: botKeys.session(sessionId),
    queryFn: () => getBotSession(sessionId),
    enabled: sessionId.length > 0,
    refetchInterval: 30_000,
  });
}

/** React Query hook fetching a bot session's live performance KPIs. */
export function useBotKpis(sessionId: string) {
  return useQuery<BotKpis>({
    queryKey: botKeys.kpis(sessionId),
    queryFn: () => getBotKpis(sessionId),
    enabled: sessionId.length > 0,
    // Live-refresh the detail KPI block ~every 30s. Pauses in the background
    // (TanStack default refetchIntervalInBackground: false).
    refetchInterval: 30_000,
  });
}

/** React Query hook fetching a bot session's value history at a resolution. */
export function useBotValueHistory(
  sessionId: string,
  resolution: BotValueResolution = 'daily',
) {
  return useQuery<BotValueHistoryResponse>({
    queryKey: botKeys.valueHistory(sessionId, resolution),
    queryFn: () => getBotValueHistory(sessionId, resolution),
    enabled: sessionId.length > 0,
    placeholderData: (prev) => prev,
  });
}

/** Default trade-ledger page size on the detail page. */
export const BOT_TRADES_PAGE_SIZE = 20;

/**
 * React Query hook fetching one page of a bot session's trade ledger. The page
 * is part of the query key so pages cache independently; `keepPreviousData`
 * keeps the table populated while the next page loads.
 */
export function useBotTrades(
  sessionId: string,
  { limit = BOT_TRADES_PAGE_SIZE, offset = 0 }: { limit?: number; offset?: number } = {},
) {
  return useQuery<BotTradeListResponse>({
    queryKey: botKeys.trades(sessionId, limit, offset),
    queryFn: () => listBotTrades(sessionId, { limit, offset }),
    enabled: sessionId.length > 0,
    placeholderData: (prev) => prev,
  });
}

/**
 * Mutation creating a bot session; refreshes the bot and dashboard views and
 * navigates to the new bot's detail page so the user lands on it immediately.
 */
export function useCreateBotSession() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation<BotSession, unknown, BotSessionCreateRequest>({
    mutationFn: (request: BotSessionCreateRequest) => createBotSession(request),
    onSuccess: (session) => {
      // A new bot adds a row to the lists and the dashboard leaderboard/equity.
      invalidateBotDependents(queryClient);
      navigate(`/bots/${session.id}`);
    },
  });
}

/** Mutation stopping a bot session; refreshes the bot and dashboard views. */
export function useStopBotSession() {
  const queryClient = useQueryClient();
  return useMutation<BotSession, unknown, string>({
    mutationFn: (sessionId: string) => stopBotSession(sessionId),
    onSuccess: () => {
      // Stopping may liquidate the open position, changing figures and equity.
      invalidateBotDependents(queryClient);
    },
  });
}

/** Mutation archiving a bot session; refreshes the bot and dashboard views. */
export function useArchiveBotSession() {
  const queryClient = useQueryClient();
  return useMutation<BotSession, unknown, string>({
    mutationFn: (sessionId: string) => archiveBotSession(sessionId),
    onSuccess: () => {
      // Archiving removes the bot from the lists and the dashboard leaderboard.
      invalidateBotDependents(queryClient);
    },
  });
}
