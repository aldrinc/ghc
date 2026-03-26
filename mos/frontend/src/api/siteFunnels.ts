import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient } from "@/api/client";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export interface SiteFunnel {
  id: string;
  siteId: string;
  name: string;
  description: string | null;
  status: "draft" | "active" | "paused" | "archived";
  entryPageId: string | null;
  productId: string | null;
  selectedOfferId: string | null;
  trackingConfig: Record<string, unknown> | null;
  createdAt: string;
  updatedAt: string;
}

export interface SiteFunnelStep {
  id: string;
  siteFunnelId: string;
  sitePageId: string;
  ordering: number;
  stepRole: string | null;
  ctaLabel: string | null;
  transitionRule: Record<string, unknown> | null;
  page: {
    id: string;
    name: string;
    slug: string;
    pageType: string | null;
  };
}

export interface SiteFunnelDetail extends SiteFunnel {
  steps: SiteFunnelStep[];
}

export interface CreateSiteFunnelRequest {
  siteId: string;
  name: string;
  description?: string;
  entryPageId?: string;
  productId?: string;
  selectedOfferId?: string;
}

export interface UpdateSiteFunnelRequest {
  name?: string;
  description?: string | null;
  status?: "draft" | "active" | "paused" | "archived";
  entryPageId?: string | null;
  productId?: string | null;
  selectedOfferId?: string | null;
  trackingConfig?: Record<string, unknown> | null;
}

export interface CreateSiteFunnelStepRequest {
  sitePageId: string;
  ordering?: number;
  stepRole?: string;
  ctaLabel?: string;
  transitionRule?: Record<string, unknown>;
}

// Get all funnels for a site
export function useSiteFunnels(siteId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SiteFunnel[]>({
    queryKey: ["sites", siteId, "funnels"],
    queryFn: () => get<SiteFunnel[]>(`/sites/${siteId}/funnels?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!siteId,
  });
}

// Get a single site funnel detail
export function useSiteFunnel(siteId: string | null | undefined, funnelId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SiteFunnelDetail>({
    queryKey: ["sites", siteId, "funnels", funnelId],
    queryFn: () => get<SiteFunnelDetail>(`/sites/${siteId}/funnels/${funnelId}?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!siteId && !!funnelId,
  });
}

// Create a new site funnel
export function useCreateSiteFunnel(siteId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: Omit<CreateSiteFunnelRequest, "siteId">) =>
      post<SiteFunnel>(`/sites/${siteId}/funnels?clientId=${workspace!.id}`, { ...request, siteId: siteId! }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels"] });
    },
  });
}

// Update a site funnel
export function useUpdateSiteFunnel(siteId: string | null | undefined, funnelId: string | null | undefined) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (payload: UpdateSiteFunnelRequest) =>
      request<SiteFunnel>(`/sites/${siteId}/funnels/${funnelId}?clientId=${workspace!.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels"] });
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
  });
}

// Delete a site funnel
export function useDeleteSiteFunnel(siteId: string | null | undefined) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (funnelId: string) =>
      request<void>(`/sites/${siteId}/funnels/${funnelId}?clientId=${workspace!.id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels"] });
    },
  });
}

// Add a step to a site funnel
export function useCreateSiteFunnelStep(siteId: string | null | undefined, funnelId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: CreateSiteFunnelStepRequest) =>
      post<SiteFunnelStep>(`/sites/${siteId}/funnels/${funnelId}/steps?clientId=${workspace!.id}`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
  });
}

// Remove a step from a site funnel
export function useDeleteSiteFunnelStep(siteId: string | null | undefined, funnelId: string | null | undefined) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (stepId: string) =>
      request<void>(`/sites/${siteId}/funnels/${funnelId}/steps/${stepId}?clientId=${workspace!.id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
  });
}

// Get all funnels across sites (for cross-site funnel index)
export function useWorkspaceSiteFunnels() {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<(SiteFunnel & { siteName?: string })[]>({
    queryKey: ["sites", "funnels", "workspace", workspace?.id],
    queryFn: () => get<(SiteFunnel & { siteName?: string })[]>(`/sites/funnels?clientId=${workspace!.id}`),
    enabled: !!workspace?.id,
  });
}
