import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  Portfolio,
  PortfolioCreate,
  PortfolioListResponse,
} from '../types/api';

/** Parameters that identify a portfolios list query. */
export interface PortfoliosListParams {
  includeLegacy: boolean;
  limit: number;
}

/** Default portfolios list parameters (matches the backend defaults). */
export const DEFAULT_PORTFOLIOS_PARAMS: PortfoliosListParams = {
  includeLegacy: true,
  limit: 50,
};

/** Typed query keys for portfolio queries. */
export const portfolioKeys = {
  all: ['portfolios'] as const,
  list: (params: PortfoliosListParams) =>
    ['portfolios', 'list', params] as const,
  detail: (id: string) => ['portfolios', 'detail', id] as const,
};

/** Fetch stored portfolios (newest first) plus the matching total. */
export async function listPortfolios(
  params: PortfoliosListParams = DEFAULT_PORTFOLIOS_PARAMS,
): Promise<PortfolioListResponse> {
  const { data } = await apiClient.get<PortfolioListResponse>(
    '/api/v1/portfolios',
    { params: { include_legacy: params.includeLegacy, limit: params.limit } },
  );
  return data;
}

/**
 * Fetch a single portfolio by id. Rejects with the axios error (404 unknown
 * portfolio) so callers can surface a specific message.
 */
export async function getPortfolio(id: string): Promise<Portfolio> {
  const { data } = await apiClient.get<Portfolio>(
    `/api/v1/portfolios/${encodeURIComponent(id)}`,
  );
  return data;
}

/**
 * Create a portfolio. Resolves to the created portfolio on 201; rejects with the
 * axios error (status 422 validation failure) so callers can surface a message.
 */
export async function createPortfolio(
  body: PortfolioCreate,
): Promise<Portfolio> {
  const { data } = await apiClient.post<Portfolio>('/api/v1/portfolios', body);
  return data;
}

/** React Query hook listing stored portfolios. */
export function usePortfolios(
  params: PortfoliosListParams = DEFAULT_PORTFOLIOS_PARAMS,
) {
  return useQuery<PortfolioListResponse>({
    queryKey: portfolioKeys.list(params),
    queryFn: () => listPortfolios(params),
  });
}

/** React Query hook fetching a single portfolio by id. */
export function usePortfolio(id: string) {
  return useQuery<Portfolio>({
    queryKey: portfolioKeys.detail(id),
    queryFn: () => getPortfolio(id),
    enabled: id.length > 0,
  });
}

/** Mutation creating a portfolio; invalidates the list on success. */
export function useCreatePortfolio() {
  const queryClient = useQueryClient();
  return useMutation<Portfolio, unknown, PortfolioCreate>({
    mutationFn: createPortfolio,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
    },
  });
}
