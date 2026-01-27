import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type {
  Funnel,
  FunnelAIChatMessage,
  FunnelDetail,
  FunnelImageAsset,
  FunnelPage,
  FunnelPageAIGenerateResponse,
  FunnelPageDetail,
  FunnelPageVersion,
} from "@/types/funnels";

export function useFunnels(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<Funnel[]>({
    queryKey: ["funnels", "list", clientId],
    queryFn: () => {
      const query = clientId ? `?clientId=${encodeURIComponent(clientId)}` : "";
      return get(`/funnels${query}`);
    },
    enabled: Boolean(clientId),
  });
}

export function useFunnel(funnelId?: string) {
  const { get } = useApiClient();
  return useQuery<FunnelDetail>({
    queryKey: ["funnels", "detail", funnelId],
    queryFn: () => get(`/funnels/${funnelId}`),
    enabled: Boolean(funnelId),
  });
}

export function useCreateFunnel() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { clientId: string; name: string; description?: string }) => post<Funnel>("/funnels", payload),
    onSuccess: (funnel) => {
      toast.success("Funnel created");
      queryClient.invalidateQueries({ queryKey: ["funnels", "list", funnel.client_id] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create funnel";
      toast.error(message);
    },
  });
}

export function useUpdateFunnel() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ funnelId, payload }: { funnelId: string; payload: Record<string, unknown> }) =>
      request<Funnel>(`/funnels/${funnelId}`, { method: "PATCH", body: JSON.stringify(payload) }),
    onSuccess: (_data, vars) => {
      toast.success("Funnel updated");
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", vars.funnelId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update funnel";
      toast.error(message);
    },
  });
}

export function useDisableFunnel() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (funnelId: string) => post<Funnel>(`/funnels/${funnelId}/disable`),
    onSuccess: (_data, funnelId) => {
      toast.success("Funnel disabled");
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", funnelId] });
    },
  });
}

export function useEnableFunnel() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (funnelId: string) => post<Funnel>(`/funnels/${funnelId}/enable`),
    onSuccess: (_data, funnelId) => {
      toast.success("Funnel enabled");
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", funnelId] });
    },
  });
}

export function usePublishFunnel() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (funnelId: string) => post<{ publicationId: string }>(`/funnels/${funnelId}/publish`),
    onSuccess: (_data, funnelId) => {
      toast.success("Funnel published");
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", funnelId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to publish funnel";
      toast.error(message);
    },
  });
}

export function useDuplicateFunnel() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ funnelId, targetCampaignId, name }: { funnelId: string; targetCampaignId?: string; name?: string }) =>
      post<Funnel>(`/funnels/${funnelId}/duplicate`, { targetCampaignId, name, copyMode: "approvedOnly", autoPublish: false }),
    onSuccess: (newFunnel) => {
      toast.success("Funnel duplicated");
      queryClient.invalidateQueries({ queryKey: ["funnels", "list", newFunnel.client_id] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to duplicate funnel";
      toast.error(message);
    },
  });
}

export function useCreateFunnelPage() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ funnelId, name }: { funnelId: string; name: string }) =>
      post<{ page: FunnelPage; draftVersion: FunnelPageVersion }>(`/funnels/${funnelId}/pages`, { name }),
    onSuccess: (_data, vars) => {
      toast.success("Page created");
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", vars.funnelId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create page";
      toast.error(message);
    },
  });
}

export function useFunnelPage(funnelId?: string, pageId?: string) {
  const { get } = useApiClient();
  return useQuery<FunnelPageDetail>({
    queryKey: ["funnels", "page", funnelId, pageId],
    queryFn: () => get(`/funnels/${funnelId}/pages/${pageId}`),
    enabled: Boolean(funnelId && pageId),
  });
}

export function useSaveFunnelDraft() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ funnelId, pageId, puckData }: { funnelId: string; pageId: string; puckData: unknown }) =>
      request<FunnelPageVersion>(`/funnels/${funnelId}/pages/${pageId}`, {
        method: "PUT",
        body: JSON.stringify({ puckData }),
      }),
    onSuccess: (_data, vars) => {
      toast.success("Draft saved");
      queryClient.invalidateQueries({ queryKey: ["funnels", "page", vars.funnelId, vars.pageId] });
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", vars.funnelId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to save draft";
      toast.error(message);
    },
  });
}

export function useApproveFunnelPage() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ funnelId, pageId }: { funnelId: string; pageId: string }) =>
      post<FunnelPageVersion>(`/funnels/${funnelId}/pages/${pageId}/approve`),
    onSuccess: (_data, vars) => {
      toast.success("Page approved");
      queryClient.invalidateQueries({ queryKey: ["funnels", "page", vars.funnelId, vars.pageId] });
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", vars.funnelId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to approve page";
      toast.error(message);
    },
  });
}

export function useUpdateFunnelPage() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ funnelId, pageId, payload }: { funnelId: string; pageId: string; payload: Record<string, unknown> }) =>
      request(`/funnels/${funnelId}/pages/${pageId}`, { method: "PATCH", body: JSON.stringify(payload) }),
    onSuccess: (_data, vars) => {
      toast.success("Page updated");
      queryClient.invalidateQueries({ queryKey: ["funnels", "page", vars.funnelId, vars.pageId] });
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", vars.funnelId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update page";
      toast.error(message);
    },
  });
}

export function useGenerateFunnelImage() {
  const { post } = useApiClient();
  return useMutation({
    mutationFn: ({ clientId, prompt }: { clientId: string; prompt: string }) =>
      post<FunnelImageAsset>("/assets/generate-image", { clientId, prompt }),
    onSuccess: () => {
      toast.success("Image generated");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to generate image";
      toast.error(message);
    },
  });
}

export function useGenerateFunnelPageAi() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      funnelId,
      pageId,
      prompt,
      messages,
      currentPuckData,
      generateImages = true,
      maxImages = 3,
    }: {
      funnelId: string;
      pageId: string;
      prompt: string;
      messages: FunnelAIChatMessage[];
      currentPuckData?: unknown;
      generateImages?: boolean;
      maxImages?: number;
    }) =>
      post<FunnelPageAIGenerateResponse>(`/funnels/${funnelId}/pages/${pageId}/ai/generate`, {
        prompt,
        messages,
        currentPuckData,
        generateImages,
        maxImages,
      }),
    onSuccess: (_data, vars) => {
      toast.success("AI draft created");
      queryClient.invalidateQueries({ queryKey: ["funnels", "page", vars.funnelId, vars.pageId] });
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", vars.funnelId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to generate AI draft";
      toast.error(message);
    },
  });
}
