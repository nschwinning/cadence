import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { apiClient } from './client';
import {
  assetKeys,
  listAssets,
  useAddAsset,
  useDeleteAsset,
} from './assets';
import { dashboardKeys } from './dashboard';
import type { AssetPage } from '../types/api';

// Mock the shared axios client rather than the network.
vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);
const mockedDelete = vi.mocked(apiClient.delete);

const emptyPage: { data: AssetPage } = { data: { items: [], total: 0 } };

/** The fixed argument shape callers always pass, varied per test. */
function baseParams() {
  return {
    limit: 20,
    offset: 0,
    search: '',
    sort: 'ticker' as const,
    direction: 'asc' as const,
    categories: [],
    sectors: [],
  };
}

describe('assetKeys factory', () => {
  it('builds stable, hierarchical query keys', () => {
    expect(assetKeys.all).toEqual(['assets']);
    expect(assetKeys.detail('AAPL')).toEqual(['assets', 'detail', 'AAPL']);

    const listParams = {
      pageSize: 20 as const,
      search: 'apple',
      sort: 'ticker' as const,
      direction: 'asc' as const,
      categories: ['stock' as const],
      sectors: ['technology' as const],
    };
    expect(assetKeys.list(listParams)).toEqual(['assets', 'list', listParams]);
  });
});

describe('listAssets URL + param serialization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGet.mockResolvedValue(emptyPage);
  });

  it('requests the assets endpoint with base paging + sort params', async () => {
    await listAssets(baseParams());

    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v1/assets',
      expect.objectContaining({
        params: expect.objectContaining({
          limit: 20,
          offset: 0,
          sort: 'ticker',
          direction: 'asc',
        }),
        // Arrays serialize as repeated keys without indices.
        paramsSerializer: { indexes: null },
      }),
    );
  });

  it('omits search/category/sector params when empty', async () => {
    await listAssets(baseParams());

    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v1/assets',
      expect.objectContaining({
        params: expect.not.objectContaining({
          search: expect.anything(),
          category: expect.anything(),
          sector: expect.anything(),
        }),
      }),
    );
  });

  it('trims the search term and sends repeated category/sector params', async () => {
    await listAssets({
      ...baseParams(),
      search: '  apple  ',
      categories: ['stock', 'etf'],
      sectors: ['technology'],
    });

    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v1/assets',
      expect.objectContaining({
        params: expect.objectContaining({
          search: 'apple',
          category: ['stock', 'etf'],
          sector: ['technology'],
        }),
      }),
    );
  });
});

describe('asset mutations refresh the composition donuts', () => {
  function wrapperWithClient() {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);
    return { wrapper, invalidateSpy };
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('invalidates both assets and dashboard metrics after adding an asset', async () => {
    mockedPost.mockResolvedValue({ data: { id: 1, ticker: 'AAPL' } });
    const { wrapper, invalidateSpy } = wrapperWithClient();

    const { result } = renderHook(() => useAddAsset(), { wrapper });
    result.current.mutate('AAPL');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: assetKeys.all });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
  });

  it('invalidates both assets and dashboard metrics after deleting an asset', async () => {
    mockedDelete.mockResolvedValue({ data: undefined });
    const { wrapper, invalidateSpy } = wrapperWithClient();

    const { result } = renderHook(() => useDeleteAsset(), { wrapper });
    result.current.mutate(1);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: assetKeys.all });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
  });
});
