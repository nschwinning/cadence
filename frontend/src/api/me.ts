import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { Me } from '../types/api';

/** Fetch the signed-in user's Cadence account. */
export async function getMe(): Promise<Me> {
  const { data } = await apiClient.get<Me>('/api/v1/me');
  return data;
}

/** React Query hook for the signed-in user's account (stable for the session). */
export function useMe() {
  return useQuery<Me>({ queryKey: ['me'], queryFn: getMe, staleTime: Infinity });
}

/**
 * Whether an object belongs to the signed-in user. Objects without an owner id
 * (older responses, fixtures) count as the user's own, so nothing is hidden by default.
 */
export function useIsOwn(ownerUserId: string | null | undefined): boolean {
  const { data: me } = useMe();
  if (!ownerUserId || !me?.user_id) return true;
  return ownerUserId === me.user_id;
}
