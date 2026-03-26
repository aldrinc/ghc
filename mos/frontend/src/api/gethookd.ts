import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type {
  GetHookdCredentialStatus,
  GetHookdSyncFeed,
  GetHookdSyncFeedRequest,
} from "@/types/assetReview";

const GETHOOKD_CREDENTIALS_QUERY_KEY = (clientId: string) => ["clients", clientId, "gethookd", "credentials"];
const GETHOOKD_FEEDS_QUERY_KEY = (clientId: string) => ["clients", clientId, "gethookd", "sync-feeds"];

/**
 * Hook to fetch GetHookd credential status.
 * The actual token is never exposed - only configuration status.
 */
export function useGetHookdCredentials(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<GetHookdCredentialStatus>({
    queryKey: clientId ? GETHOOKD_CREDENTIALS_QUERY_KEY(clientId) : ["gethookd-credentials-disabled"],
    queryFn: () => get(`/clients/${clientId}/gethookd/credentials`),
    enabled: Boolean(clientId),
  });
}

/**
 * Hook to update GetHookd API token.
 * Token is sent to backend and encrypted there.
 */
export function useUpdateGetHookdCredentials(clientId: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { apiToken: string }) => {
      return request<GetHookdCredentialStatus>(`/clients/${clientId}/gethookd/credentials`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      toast.success("GetHookd credentials updated");
      queryClient.invalidateQueries({ queryKey: GETHOOKD_CREDENTIALS_QUERY_KEY(clientId) });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update GetHookd credentials";
      toast.error(message);
    },
  });
}

/**
 * Hook to fetch GetHookd sync feeds for a client.
 */
export function useGetHookdSyncFeeds(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<GetHookdSyncFeed[]>({
    queryKey: clientId ? GETHOOKD_FEEDS_QUERY_KEY(clientId) : ["gethookd-feeds-disabled"],
    queryFn: () => get(`/clients/${clientId}/gethookd/sync-feeds`),
    enabled: Boolean(clientId),
  });
}

/**
 * Hook to create a new GetHookd sync feed.
 */
export function useCreateGetHookdSyncFeed(clientId: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: GetHookdSyncFeedRequest) => {
      return post<GetHookdSyncFeed>(`/clients/${clientId}/gethookd/sync-feeds`, payload);
    },
    onSuccess: () => {
      toast.success("Sync feed created");
      queryClient.invalidateQueries({ queryKey: GETHOOKD_FEEDS_QUERY_KEY(clientId) });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create sync feed";
      toast.error(message);
    },
  });
}

/**
 * Hook to update a GetHookd sync feed.
 */
export function useUpdateGetHookdSyncFeed(clientId: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ feedId, payload }: { feedId: string; payload: GetHookdSyncFeedRequest }) => {
      return request<GetHookdSyncFeed>(`/clients/${clientId}/gethookd/sync-feeds/${feedId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      toast.success("Sync feed updated");
      queryClient.invalidateQueries({ queryKey: GETHOOKD_FEEDS_QUERY_KEY(clientId) });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update sync feed";
      toast.error(message);
    },
  });
}

/**
 * Hook to delete a GetHookd sync feed.
 */
export function useDeleteGetHookdSyncFeed(clientId: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (feedId: string) => {
      return request(`/clients/${clientId}/gethookd/sync-feeds/${feedId}`, {
        method: "DELETE",
      });
    },
    onSuccess: () => {
      toast.success("Sync feed deleted");
      queryClient.invalidateQueries({ queryKey: GETHOOKD_FEEDS_QUERY_KEY(clientId) });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to delete sync feed";
      toast.error(message);
    },
  });
}
