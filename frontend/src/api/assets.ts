import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  Asset,
  AssetCategory,
  AssetCreate,
  AssetDetail,
  AssetPage,
  AssetSortDirection,
  AssetSortField,
  Sector,
} from '../types/api';

/** Page sizes offered to the user; kept in lockstep with the backend contract. */
export const ASSET_PAGE_SIZES = [20, 50, 100] as const;
export type AssetPageSize = (typeof ASSET_PAGE_SIZES)[number];

/**
 * The asset categories Cadence supports as user-facing choices — the single
 * source of truth for every selectable/filterable category control (the assets
 * list category filter and the recommendation-run form). Cadence supports
 * stocks and crypto only; legacy `etf`/`fund`/`other` values may still be stored
 * on existing assets and are still rendered by `CategoryBadge`, but they are not
 * offered as choices here.
 */
export const SUPPORTED_CATEGORIES = [
  'stock',
  'crypto',
] as const satisfies readonly AssetCategory[];

/** Selectable sector filter values; kept in lockstep with the backend enum. */
export const SECTORS = [
  'technology',
  'financial-services',
  'healthcare',
  'consumer-cyclical',
  'consumer-defensive',
  'industrials',
  'energy',
  'basic-materials',
  'real-estate',
  'utilities',
  'communication-services',
] as const satisfies readonly Sector[];

/** Default sort field/direction for the assets list (matches the backend). */
export const DEFAULT_ASSET_SORT: AssetSortField = 'ticker';
export const DEFAULT_ASSET_DIRECTION: AssetSortDirection = 'asc';

/** Parameters that identify a page of the assets list. */
export interface AssetsListParams {
  pageSize: AssetPageSize;
  search: string;
  sort: AssetSortField;
  direction: AssetSortDirection;
  categories: AssetCategory[];
  sectors: Sector[];
}

/** Typed query keys for assets-related queries. */
export const assetKeys = {
  all: ['assets'] as const,
  list: (params: AssetsListParams) => ['assets', 'list', params] as const,
  detail: (ticker: string) => ['assets', 'detail', ticker] as const,
};

/**
 * Fetch one page of the stored asset universe in the requested order, filtered
 * by `search`, `categories`, and `sectors`. Categories and sectors serialize as
 * repeated `category`/`sector` params (`?category=stock&sector=technology`) and
 * are each omitted entirely when empty (empty selection = all for that filter).
 */
export async function listAssets(params: {
  limit: number;
  offset: number;
  search: string;
  sort: AssetSortField;
  direction: AssetSortDirection;
  categories: AssetCategory[];
  sectors: Sector[];
}): Promise<AssetPage> {
  const query: Record<string, string | number | string[]> = {
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    direction: params.direction,
  };
  const trimmed = params.search.trim();
  if (trimmed) query.search = trimmed;
  if (params.categories.length > 0) query.category = params.categories;
  if (params.sectors.length > 0) query.sector = params.sectors;
  const { data } = await apiClient.get<AssetPage>('/api/v1/assets', {
    params: query,
    // Repeat array keys without brackets: `category=stock&sector=technology`.
    paramsSerializer: { indexes: null },
  });
  return data;
}

/**
 * Fetch a single asset's detail snapshot (native-currency price + history and
 * core facts). Rejects with the axios error (404 unknown ticker / 503 provider
 * unavailable) so callers can surface a specific message.
 */
export async function getAssetDetail(ticker: string): Promise<AssetDetail> {
  const { data } = await apiClient.get<AssetDetail>(
    `/api/v1/assets/${encodeURIComponent(ticker)}/details`,
  );
  return data;
}

/**
 * Add an asset by ticker. Resolves to the created asset on 201; rejects with the
 * axios error (status 409 duplicate / 422 unknown ticker / 503 provider or FX
 * unavailable) so callers can surface a specific message.
 */
export async function addAsset(ticker: string): Promise<Asset> {
  const body: AssetCreate = { ticker };
  const { data } = await apiClient.post<Asset>('/api/v1/assets', body);
  return data;
}

/** Permanently delete an asset by id. */
export async function deleteAsset(id: number): Promise<void> {
  await apiClient.delete(`/api/v1/assets/${id}`);
}

/**
 * Infinite-scroll hook over the stored asset universe. Fetches pages of
 * `pageSize` rows in the requested `sort`/`direction` order, filtered by
 * `search`, `categories`, and `sectors`, exposing `fetchNextPage`/`hasNextPage`
 * driven by the server-reported `total`. The query key includes every parameter,
 * so changing the sort, direction, or filters reloads from the first page.
 */
export function useAssets({
  pageSize,
  search,
  sort,
  direction,
  categories,
  sectors,
}: AssetsListParams) {
  return useInfiniteQuery({
    queryKey: assetKeys.list({
      pageSize,
      search,
      sort,
      direction,
      categories,
      sectors,
    }),
    queryFn: ({ pageParam }) =>
      listAssets({
        limit: pageSize,
        offset: pageParam,
        search,
        sort,
        direction,
        categories,
        sectors,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + page.items.length, 0);
      return loaded < lastPage.total ? loaded : undefined;
    },
  });
}

/** React Query hook fetching a single asset's detail snapshot by ticker. */
export function useAssetDetail(ticker: string) {
  return useQuery<AssetDetail>({
    queryKey: assetKeys.detail(ticker),
    queryFn: () => getAssetDetail(ticker),
    enabled: ticker.length > 0,
  });
}

/** Mutation adding an asset by ticker; invalidates the list on success. */
export function useAddAsset() {
  const queryClient = useQueryClient();
  return useMutation<Asset, unknown, string>({
    mutationFn: addAsset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: assetKeys.all });
    },
  });
}

/** Mutation deleting an asset by id; invalidates the list on success. */
export function useDeleteAsset() {
  const queryClient = useQueryClient();
  return useMutation<void, unknown, number>({
    mutationFn: deleteAsset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: assetKeys.all });
    },
  });
}
