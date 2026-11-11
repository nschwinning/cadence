import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { AdminAccount, AdminFlattenResponse } from '../types/api';

/** Typed query keys for the broker-account admin. */
export const adminKeys = {
  all: ['admin'] as const,
  account: ['admin', 'account'] as const,
};

/** Fetch the live account overview (figures, cash check, open orders, positions). */
export async function getAdminAccount(): Promise<AdminAccount> {
  const { data } = await apiClient.get<AdminAccount>('/api/v1/admin/account');
  return data;
}

/**
 * Sell the orphan excess for one symbol, or for every orphan when `symbol` is null.
 * Only the symbol is sent: the server recomputes the quantity at execution.
 */
export async function flattenOrphans(
  symbol: string | null,
): Promise<AdminFlattenResponse> {
  const { data } = await apiClient.post<AdminFlattenResponse>(
    '/api/v1/admin/flatten-orphans',
    { symbol },
  );
  return data;
}

/** React Query hook for the account overview; `refetch` drives the manual refresh. */
export function useAdminAccount() {
  return useQuery<AdminAccount>({
    queryKey: adminKeys.account,
    queryFn: getAdminAccount,
    refetchInterval: 60_000,
  });
}

/** Mutation flattening orphans; refreshes the overview once it settles. */
export function useFlattenOrphans() {
  const queryClient = useQueryClient();
  return useMutation<AdminFlattenResponse, unknown, string | null>({
    mutationFn: flattenOrphans,
    onSettled: () => queryClient.invalidateQueries({ queryKey: adminKeys.all }),
  });
}
