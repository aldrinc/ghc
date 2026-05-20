import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { toast } from "@/components/ui/toast";

function getMutationErrorMessage(err: ApiError | Error, fallback: string): string {
  const candidate = err as { message?: unknown };
  return typeof candidate.message === "string" && candidate.message ? candidate.message : fallback;
}

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
  options?: SiteFunnelStepOption[];
}

export interface SiteFunnelStepOption {
  id: string;
  siteFunnelStepId: string;
  sitePageId: string;
  optionKey: string;
  label: string;
  status: "draft" | "active" | "paused" | "archived";
  trafficWeight: number | null;
  isControl: boolean;
  metadata: Record<string, unknown>;
  page: {
    id: string;
    name: string;
    slug: string;
    pageType: string | null;
  } | null;
  createdAt: string;
  updatedAt: string;
}

export interface SiteFunnelPathStep {
  id: string;
  siteFunnelPathId: string;
  siteFunnelStepId: string;
  siteFunnelStepOptionId: string;
  sitePageId: string;
  ordering: number;
  stepRole: string | null;
  page: {
    id: string;
    name: string;
    slug: string;
    pageType: string | null;
  } | null;
  option: {
    id: string;
    optionKey: string;
    label: string;
    status: string;
  } | null;
  createdAt: string;
}

export interface SiteFunnelPath {
  id: string;
  siteFunnelId: string;
  campaignId: string | null;
  name: string;
  slug: string;
  status: "draft" | "active" | "paused" | "archived";
  trafficWeight: number | null;
  isControl: boolean;
  experimentSpecId: string | null;
  variantId: string | null;
  metadata: Record<string, unknown>;
  steps: SiteFunnelPathStep[];
  createdAt: string;
  updatedAt: string;
}

export interface SiteFunnelDetail extends SiteFunnel {
  steps: SiteFunnelStep[];
  paths: SiteFunnelPath[];
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

export interface CreateSiteFunnelStepOptionRequest {
  sitePageId: string;
  optionKey: string;
  label: string;
  status?: "draft" | "active" | "paused" | "archived";
  trafficWeight?: number | null;
  isControl?: boolean;
  metadata?: Record<string, unknown>;
}

export interface CreateSiteFunnelPathRequest {
  name: string;
  slug: string;
  status?: "draft" | "active" | "paused" | "archived";
  campaignId?: string | null;
  trafficWeight?: number | null;
  isControl?: boolean;
  experimentSpecId?: string | null;
  variantId?: string | null;
  metadata?: Record<string, unknown>;
  steps: Array<{
    siteFunnelStepId: string;
    sitePageId: string;
  }>;
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
      post<SiteFunnelDetail>(`/sites/${siteId}/funnels?clientId=${workspace!.id}`, {
        ...request,
        siteId: siteId!,
      }),
    onSuccess: () => {
      toast.success("Site funnel created");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels"] });
      queryClient.invalidateQueries({ queryKey: ["sites", "funnels", "workspace", workspace?.id] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to create site funnel"));
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
      request<SiteFunnelDetail>(`/sites/${siteId}/funnels/${funnelId}?clientId=${workspace!.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      toast.success("Site funnel updated");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels"] });
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
      queryClient.invalidateQueries({ queryKey: ["sites", "funnels", "workspace", workspace?.id] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to update site funnel"));
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
      toast.success("Site funnel deleted");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels"] });
      queryClient.invalidateQueries({ queryKey: ["sites", "funnels", "workspace", workspace?.id] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to delete site funnel"));
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
      toast.success("Funnel step added");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to add funnel step"));
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
      toast.success("Funnel step removed");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to remove funnel step"));
    },
  });
}

// Add a page option to a site funnel step
export function useCreateSiteFunnelStepOption(siteId: string | null | undefined, funnelId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: ({ stepId, request }: { stepId: string; request: CreateSiteFunnelStepOptionRequest }) =>
      post<SiteFunnelStepOption>(
        `/sites/${siteId}/funnels/${funnelId}/steps/${stepId}/options?clientId=${workspace!.id}`,
        request,
      ),
    onSuccess: () => {
      toast.success("Funnel step option added");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to add funnel step option"));
    },
  });
}

// Remove a page option from a site funnel step
export function useDeleteSiteFunnelStepOption(siteId: string | null | undefined, funnelId: string | null | undefined) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: ({ stepId, optionId }: { stepId: string; optionId: string }) =>
      request<void>(`/sites/${siteId}/funnels/${funnelId}/steps/${stepId}/options/${optionId}?clientId=${workspace!.id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success("Funnel step option removed");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to remove funnel step option"));
    },
  });
}

// Add an internal path to a site funnel
export function useCreateSiteFunnelPath(siteId: string | null | undefined, funnelId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: CreateSiteFunnelPathRequest) =>
      post<SiteFunnelPath>(`/sites/${siteId}/funnels/${funnelId}/paths?clientId=${workspace!.id}`, request),
    onSuccess: () => {
      toast.success("Funnel path created");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to create funnel path"));
    },
  });
}

// Remove an internal path from a site funnel
export function useDeleteSiteFunnelPath(siteId: string | null | undefined, funnelId: string | null | undefined) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (pathId: string) =>
      request<void>(`/sites/${siteId}/funnels/${funnelId}/paths/${pathId}?clientId=${workspace!.id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success("Funnel path removed");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnels", funnelId] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to remove funnel path"));
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
