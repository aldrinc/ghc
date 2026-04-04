import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient } from "./client";
import type {
  ClientSwipeAsset,
  CompanySwipeAsset,
  SwipeCollection,
  SwipeCollectionCloneRequest,
  SwipeCollectionCreateRequest,
  SwipeCollectionDetail,
  SwipeCollectionItemsRequest,
  SwipeReviewBulkRequest,
  SwipeReviewFilter,
} from "@/types/swipes";

export const SWIPE_COLLECTIONS_QUERY_KEY = ["swipe-collections"] as const;

export const swipeCollectionDetailQueryKey = (collectionId?: string | null) =>
  ["swipe-collection", collectionId] as const;

function buildSwipeCompanyQuery(filters?: SwipeReviewFilter) {
  const params = new URLSearchParams();
  if (!filters) return "";
  if (filters.collectionId) params.set("collection_id", filters.collectionId);
  if (filters.source === "gethookd") params.set("source", "gethookd");
  if (filters.reviewStatus && filters.reviewStatus !== "all") {
    params.set("review_status", filters.reviewStatus);
  }
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.changedSince && filters.changedSince !== "all") {
    params.set("changed_since", filters.changedSince);
  }
  if (filters.notInLaunchCollection) params.set("not_in_launch_collection", "true");
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function useClientSwipes(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ClientSwipeAsset[]>({
    queryKey: ["swipes", clientId],
    queryFn: () => get(`/swipes/client/${clientId}`),
    enabled: Boolean(clientId),
  });
}

export function useCompanySwipes(filters?: SwipeReviewFilter, enabled = true) {
  const { get } = useApiClient();
  return useQuery<CompanySwipeAsset[]>({
    queryKey: ["swipes", "company", filters],
    queryFn: () => get(`/swipes/company${buildSwipeCompanyQuery(filters)}`),
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

export function useSwipeReviewApi() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["swipes"] });
    await queryClient.invalidateQueries({ queryKey: SWIPE_COLLECTIONS_QUERY_KEY });
  };

  const makeMutation = <TPath extends string>(path: TPath) =>
    useMutation({
      mutationFn: (payload: SwipeReviewBulkRequest) => post(path, payload),
      onSuccess: () => void invalidate(),
    });

  return {
    approveSwipes: makeMutation("/swipes/review/approve"),
    rejectSwipes: makeMutation("/swipes/review/reject"),
    markPendingSwipes: makeMutation("/swipes/review/mark-pending"),
  };
}
