import axios from 'axios';
import { currentAccessToken, reportForbidden, reportUnauthorized } from '../auth/session';
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

// Send the signed-in user's access token on every request (none while login is off).
apiClient.interceptors.request.use((config) => {
  const token = currentAccessToken();
  if (token) config.headers.set('Authorization', `Bearer ${token}`);
  return config;
});

// 401: the session is gone or expired — log in again. 403: show a permission notice.
apiClient.interceptors.response.use(undefined, (error: unknown) => {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401) reportUnauthorized();
    if (error.response?.status === 403) {
      const detail = (error.response.data as { detail?: unknown } | undefined)?.detail;
      reportForbidden(typeof detail === 'string' ? detail : undefined);
    }
  }
  return Promise.reject(error);
});

/** Fetch the backend health status. Always resolves to a typed payload on 200. */
export async function getHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>('/health');
  return data;
}
