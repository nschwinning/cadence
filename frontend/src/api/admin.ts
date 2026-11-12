import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  AdminAccount,
  AdminFlattenResponse,
  AdminReconcileResult,
} from '../types/api';

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

/**
 * Buy back shortfalls/shorts for one symbol, or every eligible one when `symbol` is
 * null. Only the symbol is sent: the server recomputes the quantity at execution.
 */
export async function restorePositions(
  symbol: string | null,
): Promise<AdminFlattenResponse> {
  const { data } = await apiClient.post<AdminFlattenResponse>(
    '/api/v1/admin/restore-positions',
    { symbol },
  );
  return data;
}

/**
 * Lower crypto ledgers to the account's holding where only fee residue differs, for one
 * symbol or every eligible one. No order is sent; the server recomputes at execution.
 */
export async function writeOffPositions(
  symbol: string | null,
): Promise<AdminFlattenResponse> {
  const { data } = await apiClient.post<AdminFlattenResponse>(
    '/api/v1/admin/write-off-positions',
    { symbol },
  );
  return data;
}

/** Resolve unbooked journaled orders now. */
export async function reconcileOrders(): Promise<AdminReconcileResult> {
  const { data } = await apiClient.post<AdminReconcileResult>(
    '/api/v1/admin/reconcile-orders',
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

/** Mutation restoring shortfalls/shorts; refreshes the overview once it settles. */
export function useRestorePositions() {
  const queryClient = useQueryClient();
  return useMutation<AdminFlattenResponse, unknown, string | null>({
    mutationFn: restorePositions,
    onSettled: () => queryClient.invalidateQueries({ queryKey: adminKeys.all }),
  });
}

/** Mutation running order reconciliation; refreshes the overview once it settles. */
export function useReconcileOrders() {
  const queryClient = useQueryClient();
  return useMutation<AdminReconcileResult, unknown, void>({
    mutationFn: reconcileOrders,
    onSettled: () => queryClient.invalidateQueries({ queryKey: adminKeys.all }),
  });
}

/** Mutation writing off crypto fee residue; refreshes the overview once it settles. */
export function useWriteOffPositions() {
  const queryClient = useQueryClient();
  return useMutation<AdminFlattenResponse, unknown, string | null>({
    mutationFn: writeOffPositions,
    onSettled: () => queryClient.invalidateQueries({ queryKey: adminKeys.all }),
  });
}
