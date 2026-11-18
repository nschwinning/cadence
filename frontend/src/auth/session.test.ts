import { describe, it, expect, vi, afterEach } from 'vitest';
import MockAdapter from './testAxiosAdapter';
import { apiClient } from '../api/client';
import { FORBIDDEN_EVENT, setSessionHandlers } from './session';

describe('API client and the login session', () => {
  afterEach(() => {
    setSessionHandlers({ getToken: () => undefined, onUnauthorized: () => {} });
    MockAdapter.reset();
  });

  it('sends the access token as a bearer token', async () => {
    setSessionHandlers({ getToken: () => 'tok-123', onUnauthorized: () => {} });
    MockAdapter.respond(200, {});
    await apiClient.get('/api/v1/portfolios', { adapter: MockAdapter.adapter });
    expect(MockAdapter.lastHeaders()?.Authorization).toBe('Bearer tok-123');
  });

  it('sends no Authorization header without a session', async () => {
    MockAdapter.respond(200, {});
    await apiClient.get('/api/v1/portfolios', { adapter: MockAdapter.adapter });
    expect(MockAdapter.lastHeaders()?.Authorization).toBeUndefined();
  });

  it('starts a new login on 401', async () => {
    const onUnauthorized = vi.fn();
    setSessionHandlers({ getToken: () => 'expired', onUnauthorized });
    MockAdapter.respond(401, { detail: 'Invalid token' });
    await expect(
      apiClient.get('/api/v1/portfolios', { adapter: MockAdapter.adapter }),
    ).rejects.toThrow();
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it('raises the permission notice on 403', async () => {
    const listener = vi.fn();
    window.addEventListener(FORBIDDEN_EVENT, listener);
    MockAdapter.respond(403, { detail: "You don't have permission for this action" });
    await expect(
      apiClient.post('/api/v1/bots/sessions', {}, { adapter: MockAdapter.adapter }),
    ).rejects.toThrow();
    window.removeEventListener(FORBIDDEN_EVENT, listener);
    expect(listener).toHaveBeenCalledOnce();
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toBe(
      "You don't have permission for this action",
    );
  });
});
