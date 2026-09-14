import axios from 'axios';
import type { HealthResponse } from '../types/api';

/**
 * Single shared axios instance for all backend calls.
 *
 * `baseURL` defaults to an empty string so requests are same-origin and
 * relative, which lets the Vite dev proxy (see vite.config.ts) forward
 * `/api` and `/health` to the backend without CORS. Set `VITE_API_URL` to
 * target an absolute backend origin instead.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
});

/** Fetch the backend health status. Always resolves to a typed payload on 200. */
export async function getHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>('/health');
  return data;
}
