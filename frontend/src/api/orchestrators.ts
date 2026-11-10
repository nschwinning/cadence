import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiClient } from './client';
import { invalidateBotDependents } from './bots';
import type {
  BotOrchestrator,
  BotOrchestratorCreateRequest,
  BotOrchestratorDetail,
  BotOrchestratorListResponse,
  OrchestratorRunListResponse,
  OrchestratorRunSummary,
} from '../types/api';

const BASE = '/api/v1/bot-orchestrators';

/** Rows per page in an orchestrator's run history. */
export const ORCHESTRATOR_RUNS_PAGE_SIZE = 5;

/** How often views poll while a decision run is queued or running. */
const LIVE_RUN_POLL_MS = 3_000;

/** Typed query keys for orchestrator queries. */
export const orchestratorKeys = {
  all: ['orchestrators'] as const,
  list: (includeArchived: boolean) =>
    ['orchestrators', 'list', includeArchived] as const,
  detail: (id: string) => ['orchestrators', 'detail', id] as const,
  runs: (id: string, page: number) => ['orchestrators', 'runs', id, page] as const,
};

/** Whether a run status is still in flight (so views should keep polling). */
export function isLiveRunStatus(status: string | undefined | null): boolean {
  return status === 'queued' || status === 'running';
}

export async function listOrchestrators(
  includeArchived = false,
): Promise<BotOrchestratorListResponse> {
  const { data } = await apiClient.get<BotOrchestratorListResponse>(BASE, {
    params: includeArchived ? { include_archived: true } : {},
  });
  return data;
}

export async function getOrchestrator(id: string): Promise<BotOrchestratorDetail> {
  const { data } = await apiClient.get<BotOrchestratorDetail>(`${BASE}/${id}`);
  return data;
}

export async function createOrchestrator(
  request: BotOrchestratorCreateRequest,
): Promise<BotOrchestratorDetail> {
  const { data } = await apiClient.post<BotOrchestratorDetail>(BASE, request);
  return data;
}

export async function stopOrchestrator(id: string): Promise<BotOrchestratorDetail> {
  const { data } = await apiClient.post<BotOrchestratorDetail>(`${BASE}/${id}/stop`);
  return data;
}

export async function archiveOrchestrator(id: string): Promise<BotOrchestratorDetail> {
  const { data } = await apiClient.post<BotOrchestratorDetail>(
    `${BASE}/${id}/archive`,
  );
  return data;
}

export async function startOrchestratorRun(id: string): Promise<OrchestratorRunSummary> {
  const { data } = await apiClient.post<OrchestratorRunSummary>(`${BASE}/${id}/runs`);
  return data;
}

export async function listOrchestratorRuns(
  id: string,
  page: number,
): Promise<OrchestratorRunListResponse> {
  const { data } = await apiClient.get<OrchestratorRunListResponse>(
    `${BASE}/${id}/runs`,
    {
      params: {
        limit: ORCHESTRATOR_RUNS_PAGE_SIZE,
        offset: page * ORCHESTRATOR_RUNS_PAGE_SIZE,
      },
    },
  );
  return data;
}

/** Orchestrators (newest first); refreshes every 30s for live values. */
export function useOrchestrators(includeArchived = false) {
  return useQuery<BotOrchestratorListResponse>({
    queryKey: orchestratorKeys.list(includeArchived),
    queryFn: () => listOrchestrators(includeArchived),
    refetchInterval: 30_000,
  });
}

/** One orchestrator; polls quickly while its latest run is queued or running. */
export function useOrchestrator(id: string) {
  return useQuery<BotOrchestratorDetail>({
    queryKey: orchestratorKeys.detail(id),
    queryFn: () => getOrchestrator(id),
    enabled: id.length > 0,
    refetchInterval: (query) =>
      isLiveRunStatus(query.state.data?.last_run?.status) ? LIVE_RUN_POLL_MS : 30_000,
  });
}

/** One page of an orchestrator's run history; polls while a run is in flight. */
export function useOrchestratorRuns(id: string, page: number, live: boolean) {
  return useQuery<OrchestratorRunListResponse>({
    queryKey: orchestratorKeys.runs(id, page),
    queryFn: () => listOrchestratorRuns(id, page),
    enabled: id.length > 0,
    refetchInterval: live ? LIVE_RUN_POLL_MS : false,
  });
}

/** Deploy an orchestrator, then open its detail view. */
export function useCreateOrchestrator() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation<BotOrchestratorDetail, unknown, BotOrchestratorCreateRequest>({
    mutationFn: createOrchestrator,
    onSuccess: (orchestrator) => {
      queryClient.invalidateQueries({ queryKey: orchestratorKeys.all });
      navigate(`/orchestrators/${orchestrator.id}`);
    },
  });
}

/** Stop an orchestrator (and its bots); refreshes orchestrator and bot views. */
export function useStopOrchestrator() {
  const queryClient = useQueryClient();
  return useMutation<BotOrchestrator, unknown, string>({
    mutationFn: stopOrchestrator,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orchestratorKeys.all });
      invalidateBotDependents(queryClient);
    },
  });
}

/** Archive a stopped orchestrator. */
export function useArchiveOrchestrator() {
  const queryClient = useQueryClient();
  return useMutation<BotOrchestrator, unknown, string>({
    mutationFn: archiveOrchestrator,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orchestratorKeys.all });
    },
  });
}

/** Queue a manual decision run; the detail view then polls until it finishes. */
export function useStartOrchestratorRun() {
  const queryClient = useQueryClient();
  return useMutation<OrchestratorRunSummary, unknown, string>({
    mutationFn: startOrchestratorRun,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orchestratorKeys.all });
      invalidateBotDependents(queryClient);
    },
  });
}
