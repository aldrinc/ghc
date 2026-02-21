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
  FunnelTemplateDetail,
  FunnelTemplateSummary,
} from "@/types/funnels";

type FunnelFilters = {
  clientId?: string;
  productId?: string;
  campaignId?: string;
  experimentId?: string;
};

type PublishFunnelDeployPayload = {
  workloadName: string;
  planPath?: string;
  instanceName?: string;
  createIfMissing?: boolean;
  inPlace?: boolean;
  applyPlan?: boolean;
  serverNames?: string[];
  https?: boolean;
  destinationPath?: string;
  upstreamBaseUrl?: string;
  upstreamApiBaseUrl?: string;
};

type PublishFunnelPayload = {
  deploy?: PublishFunnelDeployPayload;
};

type PublishFunnelApplyResponse = {
  mode?: string;
  jobId?: string;
  status?: string;
  statusPath?: string;
  accessUrls?: string[];
  [key: string]: unknown;
};

type PublishFunnelResponse = {
  publicationId?: string | null;
  deploy?: {
    patch?: Record<string, unknown>;
    apply?: PublishFunnelApplyResponse;
  };
};

const buildFunnelsPath = (filters: FunnelFilters) => {
  const params = new URLSearchParams();
  if (filters.clientId) params.set("clientId", filters.clientId);
  if (filters.productId) params.set("productId", filters.productId);
  if (filters.campaignId) params.set("campaignId", filters.campaignId);
  if (filters.experimentId) params.set("experimentId", filters.experimentId);
  const qs = params.toString();
  return qs ? `/funnels?${qs}` : "/funnels";
};

export function useFunnels(filters?: FunnelFilters | string) {
  const { get } = useApiClient();
  const resolvedFilters = typeof filters === "string" ? { clientId: filters } : (filters ?? {});
  const enabled = Boolean(
    resolvedFilters.campaignId ||
      resolvedFilters.experimentId ||
      (resolvedFilters.clientId && resolvedFilters.productId)
  );
  return useQuery<Funnel[]>({
    queryKey: [
      "funnels",
      "list",
      resolvedFilters.clientId ?? null,
      resolvedFilters.productId ?? null,
      resolvedFilters.campaignId ?? null,
      resolvedFilters.experimentId ?? null,
    ],
    queryFn: () => get(buildFunnelsPath(resolvedFilters)),
    enabled,
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
    mutationFn: (payload: {
      clientId: string;
      productId: string;
      selectedOfferId?: string | null;
      name: string;
      description?: string;
      campaignId?: string | null;
    }) =>
      post<Funnel>("/funnels", payload),
    onSuccess: (funnel) => {
      toast.success("Funnel created");
      queryClient.invalidateQueries({
        queryKey: ["funnels", "list", funnel.client_id ?? null, funnel.product_id ?? null, null],
      });
      queryClient.invalidateQueries({
        queryKey: [
          "funnels",
          "list",
          funnel.client_id ?? null,
          funnel.product_id ?? null,
          funnel.campaign_id ?? null,
        ],
      });
      if (funnel.campaign_id) {
        queryClient.invalidateQueries({
          queryKey: ["funnels", "list", null, null, funnel.campaign_id],
        });
      }
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
    mutationFn: ({ funnelId, payload }: { funnelId: string; payload?: PublishFunnelPayload }) =>
      post<PublishFunnelResponse>(`/funnels/${funnelId}/publish`, payload),
    onSuccess: (data, vars) => {
      if (data.deploy?.apply?.mode === "async") {
        toast.success("Funnel published and deploy started");
      } else {
        toast.success("Funnel published");
      }
      queryClient.invalidateQueries({ queryKey: ["funnels", "detail", vars.funnelId] });
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
      queryClient.invalidateQueries({ queryKey: ["funnels", "list", newFunnel.client_id ?? null, null] });
      queryClient.invalidateQueries({ queryKey: ["funnels", "list", newFunnel.client_id ?? null, newFunnel.campaign_id ?? null] });
      if (newFunnel.campaign_id) {
        queryClient.invalidateQueries({ queryKey: ["funnels", "list", null, newFunnel.campaign_id] });
      }
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to duplicate funnel";
      toast.error(message);
    },
  });
}

export function useDeleteFunnel() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ funnelId }: { funnelId: string }) =>
      request<void>(`/funnels/${funnelId}`, { method: "DELETE" }),
    onSuccess: (_data, vars) => {
      toast.success("Funnel deleted");
      queryClient.invalidateQueries({ queryKey: ["funnels"] });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      queryClient.removeQueries({ queryKey: ["funnels", "detail", vars.funnelId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to delete funnel";
      toast.error(message);
    },
  });
}

export function useCreateFunnelPage() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ funnelId, name, templateId }: { funnelId: string; name: string; templateId?: string }) =>
      post<{ page: FunnelPage; draftVersion: FunnelPageVersion }>(`/funnels/${funnelId}/pages`, { name, templateId }),
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

export function useFunnelTemplates() {
  const { get } = useApiClient();
  return useQuery<FunnelTemplateSummary[]>({
    queryKey: ["funnels", "templates"],
    queryFn: () => get("/funnels/templates"),
  });
}

export function useFunnelTemplate(templateId?: string) {
  const { get } = useApiClient();
  return useQuery<FunnelTemplateDetail>({
    queryKey: ["funnels", "templates", templateId],
    queryFn: () => get(`/funnels/templates/${templateId}`),
    enabled: Boolean(templateId),
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
