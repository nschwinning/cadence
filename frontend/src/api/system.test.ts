import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from './client';
import { systemKeys, getSystemStatus } from './system';
import type { SystemStatusResponse } from '../types/api';

// Mock the shared axios client rather than the network.
vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

const mockedGet = vi.mocked(apiClient.get);

const sampleResponse: { data: SystemStatusResponse } = {
  data: {
    backends: [
      {
        name: 'Alpaca',
        configured: true,
        identifier: 'paper',
        reachable: true,
        latency_ms: 42.5,
        detail: null,
      },
    ],
  },
};

describe('systemKeys factory', () => {
  it('builds stable query keys', () => {
    expect(systemKeys.all).toEqual(['system']);
    expect(systemKeys.status).toEqual(['system', 'status']);
  });
});

describe('getSystemStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('GETs the status endpoint and returns the payload', async () => {
    mockedGet.mockResolvedValueOnce(sampleResponse);

    const result = await getSystemStatus();

    expect(mockedGet).toHaveBeenCalledWith('/api/v1/system/status');
    expect(result).toEqual(sampleResponse.data);
  });
});
