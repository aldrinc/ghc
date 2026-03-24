import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "./client";
import type {
  ClientSwipeAsset,
  CompanySwipeAsset,
  SwipeCollection,
  SwipeCollectionCloneRequest,
  SwipeCollectionCreateRequest,
  SwipeCollectionDetail,
  SwipeCollectionItemsRequest,
} from "@/types/swipes";

export const SWIPE_COLLECTIONS_QUERY_KEY = ["swipe-collections"] as const;

export const swipeCollectionDetailQueryKey = (collectionId?: string | null) =>
  ["swipe-collection", collectionId] as const;

export function useClientSwipes(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ClientSwipeAsset[]>({
    queryKey: ["swipes", clientId],
    queryFn: () => get(`/swipes/client/${clientId}`),
    enabled: Boolean(clientId),
  });
}

export function useCompanySwipes(enabled = true) {
  const { get } = useApiClient();
  return useQuery<CompanySwipeAsset[]>({
    queryKey: ["swipes", "company"],
    queryFn: () => get("/swipes/company"),
    enabled,
  });
}

export function useSwipeCollections(enabled = true) {
  const { get } = useApiClient();
  return useQuery<SwipeCollection[]>({
    queryKey: SWIPE_COLLECTIONS_QUERY_KEY,
    queryFn: () => get("/swipes/collections"),
    enabled,
  });
}

export function useSwipeCollection(collectionId?: string | null, enabled = true) {
  const { get } = useApiClient();
  return useQuery<SwipeCollectionDetail>({
    queryKey: swipeCollectionDetailQueryKey(collectionId),
    queryFn: () => get(`/swipes/collections/${collectionId}`),
    enabled: enabled && Boolean(collectionId),
  });
}

export function useSwipeCollectionsApi() {
  const { post, request } = useApiClient();

  return {
    createSwipeCollection: (payload: SwipeCollectionCreateRequest) =>
      post<SwipeCollection>("/swipes/collections", payload),
    cloneSwipeCollection: (collectionId: string, payload: SwipeCollectionCloneRequest) =>
      post<SwipeCollection>(`/swipes/collections/${collectionId}/clone`, payload),
    addSwipesToCollection: (collectionId: string, payload: SwipeCollectionItemsRequest) =>
      post<SwipeCollection>(`/swipes/collections/${collectionId}/items`, payload),
    removeSwipeFromCollection: (collectionId: string, swipeAssetId: string) =>
      request<SwipeCollection>(`/swipes/collections/${collectionId}/items/${swipeAssetId}`, {
        method: "DELETE",
      }),
  };
}
