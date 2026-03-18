import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/clerk-react";
import { useApiClient, type ApiError } from "@/api/client";
import type { Client } from "@/types/common";
import { toast } from "@/components/ui/toast";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";

const defaultBaseUrl = resolveRequiredApiBaseUrl();
const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";

export type ShopifyConnectionState =
  | "not_connected"
  | "installed_missing_storefront_token"
  | "multiple_installations_conflict"
  | "ready"
  | "error";

export type ShopifyInstallationState =
  | "not_installed"
  | "conflict"
  | "installed_missing_storefront_token"
  | "installed"
  | "error";

export type ClientShopifyStatus = {
  state: ShopifyConnectionState;
  message: string;
  shopDomain?: string | null;
  displayShopDomain?: string | null;
  shopDomains: string[];
  displayShopDomains: string[];
  selectedShopDomain?: string | null;
  hasStorefrontAccessToken: boolean;
  missingScopes: string[];
  installationState: ShopifyInstallationState;
};

export type ClientShopifyInstallUrlResponse = {
  installUrl: string;
};

export type ClientShopifyAppCredentials = {
  apiKey?: string | null;
  hasApiSecret: boolean;
  isConfigured: boolean;
  updatedAt?: string | null;
};

export type ClientShopifyCatalogProduct = {
  productGid: string;
  title: string;
  handle: string;
  status: string;
};

export type ClientShopifyProductsResponse = {
  shopDomain: string;
  products: ClientShopifyCatalogProduct[];
};

export type ClientShopifyCreatedVariant = {
  variantGid: string;
  title: string;
  priceCents: number;
  currency: string;
};

export type ClientShopifyCreateProductPayload = {
  title: string;
  description?: string;
  handle?: string;
  vendor?: string;
  productType?: string;
  tags?: string[];
  status?: "ACTIVE" | "DRAFT";
  variants: Array<{ title: string; priceCents: number; currency: string }>;
  shopDomain?: string;
};

export type ClientShopifyCreateProductResponse = {
  shopDomain: string;
  productGid: string;
  title: string;
  handle: string;
  status: string;
  variants: ClientShopifyCreatedVariant[];
};

export type ClientShopifyThemeBrandSyncPayload = {
  designSystemId?: string;
  productId?: string;
  componentImageAssetMap?: Record<string, string>;
  shopDomain?: string;
  themeId?: string;
  themeName?: string;
};

export type ClientShopifyThemeCoverageSummary = {
  requiredSourceVars: string[];
  requiredThemeVars: string[];
  missingSourceVars: string[];
  missingThemeVars: string[];
};

export type ClientShopifyThemeSettingsSyncSummary = {
  settingsFilename?: string | null;
  expectedPaths: string[];
  updatedPaths: string[];
  missingPaths: string[];
  requiredMissingPaths: string[];
  semanticUpdatedPaths: string[];
  unmappedColorPaths: string[];
  semanticTypographyUpdatedPaths: string[];
  unmappedTypographyPaths: string[];
};

export type ClientShopifyThemeSettingsAuditSummary = {
  settingsFilename?: string | null;
  expectedPaths: string[];
  syncedPaths: string[];
  mismatchedPaths: string[];
  missingPaths: string[];
  requiredMissingPaths: string[];
  requiredMismatchedPaths: string[];
  semanticSyncedPaths: string[];
  semanticMismatchedPaths: string[];
  unmappedColorPaths: string[];
  semanticTypographySyncedPaths: string[];
  semanticTypographyMismatchedPaths: string[];
  unmappedTypographyPaths: string[];
};

export type ClientShopifyThemeBrandSyncResponse = {
  shopDomain: string;
  workspaceName: string;
  designSystemId: string;
  designSystemName: string;
  brandName: string;
  logoAssetPublicId: string;
  logoUrl: string;
  themeId: string;
  themeName: string;
  themeRole: string;
  layoutFilename: string;
  cssFilename: string;
  settingsFilename?: string | null;
  jobId?: string | null;
  coverage: ClientShopifyThemeCoverageSummary;
  settingsSync: ClientShopifyThemeSettingsSyncSummary;
};

export type ClientShopifyThemeTemplateBuildPayload = {
  draftId?: string;
  designSystemId?: string;
  productId?: string;
  componentImageAssetMap?: Record<string, string>;
  componentTextValues?: Record<string, string>;
  featureHighlights?: ClientShopifyThemeTemplateFeatureHighlights;
  shopDomain?: string;
  themeId?: string;
  themeName?: string;
};

export type ClientShopifyThemeTemplateImageSlot = {
  path: string;
  key: string;
  role: string;
  recommendedAspect: string;
  currentValue?: string | null;
};

export type ClientShopifyThemeTemplateTextSlot = {
  path: string;
  key: string;
  currentValue?: string | null;
};

export type ClientShopifyThemeTemplateFeatureHighlightCard = {
  header?: string | null;
  subtext?: string | null;
};

export type ClientShopifyThemeTemplateFeatureHighlights = {
  card1?: ClientShopifyThemeTemplateFeatureHighlightCard | null;
  card2?: ClientShopifyThemeTemplateFeatureHighlightCard | null;
  card3?: ClientShopifyThemeTemplateFeatureHighlightCard | null;
  card4?: ClientShopifyThemeTemplateFeatureHighlightCard | null;
};

export type ClientShopifyThemeTemplateDraftData = {
  shopDomain: string;
  workspaceName: string;
  designSystemId: string;
  designSystemName: string;
  brandName: string;
  logoAssetPublicId: string;
  logoUrl: string;
  themeId: string;
  themeName: string;
  themeRole: string;
  cssVars: Record<string, string>;
  fontUrls: string[];
  dataTheme: string;
  productId?: string | null;
  componentImageAssetMap: Record<string, string>;
  componentTextValues: Record<string, string>;
  featureHighlights?: ClientShopifyThemeTemplateFeatureHighlights | null;
  imageSlots: ClientShopifyThemeTemplateImageSlot[];
  textSlots: ClientShopifyThemeTemplateTextSlot[];
  metadata: Record<string, unknown>;
};

export type ClientShopifyThemeTemplateDraftVersion = {
  id: string;
  draftId: string;
  versionNumber: number;
  source: string;
  notes?: string | null;
  createdByUserExternalId?: string | null;
  createdAt: string;
  data: ClientShopifyThemeTemplateDraftData;
};

export type ClientShopifyThemeTemplateDraft = {
  id: string;
  status: string;
  shopDomain: string;
  themeId: string;
  themeName: string;
  themeRole: string;
  designSystemId?: string | null;
  productId?: string | null;
  createdByUserExternalId?: string | null;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string | null;
  latestVersion?: ClientShopifyThemeTemplateDraftVersion | null;
};

export type ClientShopifyThemeTemplateBuildResponse = {
  draft: ClientShopifyThemeTemplateDraft;
  version: ClientShopifyThemeTemplateDraftVersion;
};

export type ClientShopifyThemeTemplateDraftUpdatePayload = {
  componentImageAssetMap?: Record<string, string>;
  componentTextValues?: Record<string, string>;
  featureHighlights?: ClientShopifyThemeTemplateFeatureHighlights;
  notes?: string;
};

export type ClientShopifyThemeTemplateGenerateImagesPayload = {
  draftId: string;
  productId?: string;
  slotPaths?: string[];
  featureHighlights?: ClientShopifyThemeTemplateFeatureHighlights;
};

export type ClientShopifyThemeTemplateGenerateImagesResponse = {
  draft: ClientShopifyThemeTemplateDraft;
  version: ClientShopifyThemeTemplateDraftVersion;
  generatedImageCount: number;
  generatedTextCount: number;
  copyAgentModel?: string | null;
  requestedImageModel?: string | null;
  requestedImageModelSource?: string | null;
  generatedSlotPaths: string[];
  imageModels: string[];
  imageModelBySlotPath: Record<string, string>;
  imageSourceBySlotPath: Record<string, string>;
  promptTokenCountBySlotPath: Record<string, number>;
  promptTokenCountTotal: number;
  rateLimitedSlotPaths: string[];
  remainingSlotPaths: string[];
  quotaExhaustedSlotPaths: string[];
  slotErrorsByPath: Record<string, string>;
  imageGenerationError?: string | null;
  copyGenerationError?: string | null;
};

export type ClientShopifyThemeTemplatePublishPayload = {
  draftId: string;
};

export type ClientShopifyThemeTemplatePublishResponse = {
  draft: ClientShopifyThemeTemplateDraft;
  version: ClientShopifyThemeTemplateDraftVersion;
  sync: ClientShopifyThemeBrandSyncResponse;
};

type ClientShopifyThemeBrandSyncJobStatus = "queued" | "running" | "succeeded" | "failed";

type ClientShopifyThemeBrandSyncJobStartResponse = {
  jobId: string;
  status: ClientShopifyThemeBrandSyncJobStatus;
  statusPath: string;
};

type ClientShopifyThemeBrandSyncJobProgress = {
  stage?: string | null;
  message?: string | null;
  totalImageSlots?: number | null;
  completedImageSlots?: number | null;
  generatedImageCount?: number | null;
  skippedImageCount?: number | null;
  updatedAt?: string | null;
};

type ClientShopifyThemeBrandSyncJobStatusResponse = {
  jobId: string;
  status: ClientShopifyThemeBrandSyncJobStatus;
  error?: string | null;
  progress?: ClientShopifyThemeBrandSyncJobProgress | null;
  result?: ClientShopifyThemeBrandSyncResponse | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
};

export type ClientShopifyThemeTemplateBuildJobStartResponse = {
  jobId: string;
  status: ClientShopifyThemeBrandSyncJobStatus;
  statusPath: string;
};

export type ClientShopifyThemeTemplateBuildJobStatusResponse = {
  jobId: string;
  status: ClientShopifyThemeBrandSyncJobStatus;
  error?: string | null;
  progress?: ClientShopifyThemeBrandSyncJobProgress | null;
  result?: ClientShopifyThemeTemplateBuildResponse | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
};

type ClientShopifyThemeTemplatePublishJobStartResponse = {
  jobId: string;
  status: ClientShopifyThemeBrandSyncJobStatus;
  statusPath: string;
};

type ClientShopifyThemeTemplatePublishJobStatusResponse = {
  jobId: string;
  status: ClientShopifyThemeBrandSyncJobStatus;
  error?: string | null;
  progress?: ClientShopifyThemeBrandSyncJobProgress | null;
  result?: ClientShopifyThemeTemplatePublishResponse | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
};

type ClientShopifyThemeTemplateGenerateImagesJobStartResponse = {
  jobId: string;
  status: ClientShopifyThemeBrandSyncJobStatus;
  statusPath: string;
};

type ClientShopifyThemeTemplateGenerateImagesJobStatusResponse = {
  jobId: string;
  status: ClientShopifyThemeBrandSyncJobStatus;
  error?: string | null;
  progress?: ClientShopifyThemeBrandSyncJobProgress | null;
  result?: ClientShopifyThemeTemplateGenerateImagesResponse | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
};

export type ClientShopifyThemeBrandAuditResponse = {
  shopDomain: string;
  workspaceName: string;
  designSystemId: string;
  designSystemName: string;
  themeId: string;
  themeName: string;
  themeRole: string;
  layoutFilename: string;
  cssFilename: string;
  settingsFilename?: string | null;
  hasManagedMarkerBlock: boolean;
  layoutIncludesManagedCssAsset: boolean;
  managedCssAssetExists: boolean;
  coverage: ClientShopifyThemeCoverageSummary;
  settingsAudit: ClientShopifyThemeSettingsAuditSummary;
  isReady: boolean;
};

export function useClients() {
  const { get } = useApiClient();
  return useQuery<Client[]>({
    queryKey: ["clients"],
    queryFn: () => get("/clients"),
  });
}

export function useClient(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<Client>({
    queryKey: ["clients", clientId],
    queryFn: () => get(`/clients/${clientId}`),
    enabled: Boolean(clientId),
  });
}

export function useClientShopifyStatus(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ClientShopifyStatus>({
    queryKey: ["clients", "shopify-status", clientId],
    queryFn: () => get(`/clients/${clientId}/shopify/status`),
    enabled: Boolean(clientId),
  });
}

export function useClientShopifyAppCredentials(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ClientShopifyAppCredentials>({
    queryKey: ["clients", "shopify-app-credentials", clientId],
    queryFn: () => get(`/clients/${clientId}/shopify/app-credentials`),
    enabled: Boolean(clientId),
  });
}

export function useUpdateClientShopifyAppCredentials(clientId: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { apiKey: string; apiSecret: string }) => {
      if (!clientId) throw new Error("Client ID is required.");
      return request<ClientShopifyAppCredentials>(`/clients/${clientId}/shopify/app-credentials`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      toast.success("Shopify app credentials saved");
      queryClient.invalidateQueries({ queryKey: ["clients", "shopify-app-credentials", clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to save Shopify app credentials";
      toast.error(message);
    },
  });
}

export function useCreateClientShopifyInstallUrl(clientId: string) {
  const { post } = useApiClient();

  return useMutation({
    mutationFn: (payload: { shopDomain: string }) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<ClientShopifyInstallUrlResponse>(`/clients/${clientId}/shopify/install-url`, payload);
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create Shopify install URL";
      toast.error(message);
    },
  });
}

export function useUpdateClientShopifyInstallation(clientId: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { shopDomain: string; storefrontAccessToken: string }) => {
      if (!clientId) throw new Error("Client ID is required.");
      return request<ClientShopifyStatus>(`/clients/${clientId}/shopify/installation`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: (_status) => {
      toast.success("Shopify installation updated");
      queryClient.invalidateQueries({ queryKey: ["clients", "shopify-status", clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update Shopify installation";
      toast.error(message);
    },
  });
}

export function useAutoProvisionClientShopifyStorefrontToken(clientId: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { shopDomain: string }) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<ClientShopifyStatus>(
        `/clients/${clientId}/shopify/installation/auto-storefront-token`,
        payload
      );
    },
    onSuccess: () => {
      toast.success("Automatic storefront token setup complete");
      queryClient.invalidateQueries({ queryKey: ["clients", "shopify-status", clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message =
        "message" in err
          ? err.message
          : err?.message || "Failed to retry automatic storefront token setup";
      toast.error(message);
    },
  });
}

export function useDisconnectClientShopifyInstallation(clientId: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { shopDomain: string }) => {
      if (!clientId) throw new Error("Client ID is required.");
      return request<ClientShopifyStatus>(`/clients/${clientId}/shopify/installation`, {
        method: "DELETE",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      toast.success("Shopify store disconnected");
      queryClient.invalidateQueries({ queryKey: ["clients", "shopify-status", clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to disconnect Shopify store";
      toast.error(message);
    },
  });
}

export function useSetClientShopifyDefaultShop(clientId: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { shopDomain: string }) => {
      if (!clientId) throw new Error("Client ID is required.");
      return request<ClientShopifyStatus>(`/clients/${clientId}/shopify/default-shop`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      toast.success("Default Shopify store saved");
      queryClient.invalidateQueries({ queryKey: ["clients", "shopify-status", clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to set default Shopify store";
      toast.error(message);
    },
  });
}

export function useListClientShopifyProducts(clientId: string) {
  const { get } = useApiClient();

  return useMutation({
    mutationFn: async (payload?: { query?: string; shopDomain?: string; limit?: number }) => {
      if (!clientId) throw new Error("Client ID is required.");
      const params = new URLSearchParams();
      if (payload?.query?.trim()) params.set("query", payload.query.trim());
      if (payload?.shopDomain?.trim()) params.set("shopDomain", payload.shopDomain.trim());
      if (payload?.limit !== undefined) params.set("limit", String(payload.limit));
      const queryString = params.toString();
      return get<ClientShopifyProductsResponse>(
        `/clients/${clientId}/shopify/products${queryString ? `?${queryString}` : ""}`,
      );
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to load Shopify products";
      toast.error(message);
    },
  });
}

export function useCreateClientShopifyProduct(clientId: string) {
  const { post } = useApiClient();

  return useMutation({
    mutationFn: (payload: ClientShopifyCreateProductPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<ClientShopifyCreateProductResponse>(`/clients/${clientId}/shopify/products`, payload);
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create Shopify product";
      toast.error(message);
    },
  });
}

export function useSyncClientShopifyThemeBrand(clientId?: string) {
  const { get, post } = useApiClient();

  return useMutation({
    mutationFn: async (payload: ClientShopifyThemeBrandSyncPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      const startResponse = await post<ClientShopifyThemeBrandSyncJobStartResponse>(
        `/clients/${clientId}/shopify/theme/brand/sync-async`,
        payload,
      );
      const syncJobId = startResponse.jobId;
      if (!syncJobId || !syncJobId.trim()) {
        throw new Error("Shopify theme sync job was not started.");
      }

      const pollTimeoutMs = 1000 * 60 * 20;
      const pollIntervalMs = 2000;
      const startedAt = Date.now();

      while (true) {
        const statusResponse = await get<ClientShopifyThemeBrandSyncJobStatusResponse>(
          `/clients/${clientId}/shopify/theme/brand/sync-jobs/${syncJobId}`,
        );
        if (statusResponse.status === "succeeded") {
          if (statusResponse.result) return statusResponse.result;
          throw new Error("Shopify theme sync completed but no result payload was returned.");
        }
        if (statusResponse.status === "failed") {
          const errorMessage = statusResponse.error?.trim();
          throw new Error(errorMessage || "Shopify theme sync failed.");
        }
        if (Date.now() - startedAt > pollTimeoutMs) {
          throw new Error("Timed out waiting for Shopify theme sync to complete.");
        }
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      }
    },
    onSuccess: (response) => {
      toast.success(`Synced Shopify theme brand for ${response.shopDomain}`);
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to sync Shopify theme brand";
      toast.error(message);
    },
  });
}

export function useListClientShopifyThemeTemplateDrafts(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ClientShopifyThemeTemplateDraft[]>({
    queryKey: ["clients", "shopify-theme-template-drafts", clientId],
    queryFn: () => get(`/clients/${clientId}/shopify/theme/brand/template/drafts`),
    enabled: Boolean(clientId),
  });
}

export function useBuildClientShopifyThemeTemplateDraft(clientId?: string) {
  const { get, post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: ClientShopifyThemeTemplateBuildPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      const startResponse = await post<ClientShopifyThemeTemplateBuildJobStartResponse>(
        `/clients/${clientId}/shopify/theme/brand/template/build-async`,
        payload,
      );
      const buildJobId = startResponse.jobId;
      if (!buildJobId || !buildJobId.trim()) {
        throw new Error("Shopify template build job was not started.");
      }

      const pollTimeoutMs = 1000 * 60 * 90;
      const pollIntervalMs = 2000;
      const startedAt = Date.now();

      while (true) {
        const statusResponse = await get<ClientShopifyThemeTemplateBuildJobStatusResponse>(
          `/clients/${clientId}/shopify/theme/brand/template/build-jobs/${buildJobId}`,
        );
        if (statusResponse.status === "succeeded") {
          if (statusResponse.result) return statusResponse.result;
          throw new Error("Shopify template build completed but no result payload was returned.");
        }
        if (statusResponse.status === "failed") {
          const errorMessage = statusResponse.error?.trim();
          throw new Error(errorMessage || "Shopify template build failed.");
        }
        if (Date.now() - startedAt > pollTimeoutMs) {
          throw new Error("Timed out waiting for Shopify template build to complete.");
        }
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      }
    },
    onSuccess: (response) => {
      toast.success(
        `Built template draft v${response.version.versionNumber} for ${response.draft.themeName}`,
      );
      queryClient.invalidateQueries({
        queryKey: ["clients", "shopify-theme-template-drafts", clientId],
      });
    },
    onError: (err: ApiError | Error) => {
      const message =
        "message" in err ? err.message : err?.message || "Failed to build Shopify theme template draft";
      toast.error(message);
    },
  });
}

export function useEnqueueClientShopifyThemeTemplateBuildJob(clientId?: string) {
  const { post } = useApiClient();

  return useMutation({
    mutationFn: async (payload: ClientShopifyThemeTemplateBuildPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      const startResponse = await post<ClientShopifyThemeTemplateBuildJobStartResponse>(
        `/clients/${clientId}/shopify/theme/brand/template/build-async`,
        payload,
      );
      const buildJobId = startResponse.jobId;
      if (!buildJobId || !buildJobId.trim()) {
        throw new Error("Shopify template build job was not started.");
      }
      return startResponse;
    },
    onError: (err: ApiError | Error) => {
      const message =
        "message" in err ? err.message : err?.message || "Failed to start Shopify template build job";
      toast.error(message);
    },
  });
}

export function useClientShopifyThemeTemplateBuildJobStatus(
  clientId?: string,
  jobId?: string,
  options?: { enabled?: boolean; refetchIntervalMs?: number },
) {
  const { get } = useApiClient();
  const shouldEnable = Boolean(clientId && jobId && (options?.enabled ?? true));
  const refetchIntervalMs = options?.refetchIntervalMs ?? 2000;

  return useQuery<ClientShopifyThemeTemplateBuildJobStatusResponse>({
    queryKey: ["clients", "shopify-theme-template-build-job", clientId, jobId],
    queryFn: () => get(`/clients/${clientId}/shopify/theme/brand/template/build-jobs/${jobId}`),
    enabled: shouldEnable,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return refetchIntervalMs;
      return status === "queued" || status === "running" ? refetchIntervalMs : false;
    },
  });
}

export function useUpdateClientShopifyThemeTemplateDraft(clientId?: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      draftId,
      payload,
      suppressSuccessToast,
    }: {
      draftId: string;
      payload: ClientShopifyThemeTemplateDraftUpdatePayload;
      suppressSuccessToast?: boolean;
    }) => {
      if (!clientId) throw new Error("Client ID is required.");
      if (!draftId?.trim()) throw new Error("Draft ID is required.");
      return request<ClientShopifyThemeTemplateDraft>(
        `/clients/${clientId}/shopify/theme/brand/template/drafts/${draftId}`,
        {
          method: "PUT",
          body: JSON.stringify(payload),
        },
      );
    },
    onSuccess: (_response, vars) => {
      if (!vars.suppressSuccessToast) {
        toast.success("Template draft updated");
      }
      queryClient.invalidateQueries({
        queryKey: ["clients", "shopify-theme-template-drafts", clientId],
      });
    },
    onError: (err: ApiError | Error) => {
      const message =
        "message" in err ? err.message : err?.message || "Failed to update Shopify template draft";
      toast.error(message);
    },
  });
}

export function usePublishClientShopifyThemeTemplateDraft(clientId?: string) {
  const { get, post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: ClientShopifyThemeTemplatePublishPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      const startResponse = await post<ClientShopifyThemeTemplatePublishJobStartResponse>(
        `/clients/${clientId}/shopify/theme/brand/template/publish-async`,
        payload,
      );
      const publishJobId = startResponse.jobId;
      if (!publishJobId || !publishJobId.trim()) {
        throw new Error("Shopify template publish job was not started.");
      }

      const pollTimeoutMs = 1000 * 60 * 20;
      const pollIntervalMs = 2000;
      const startedAt = Date.now();
      const maxConsecutiveTransientFailures = 8;
      let consecutiveTransientFailures = 0;

      while (true) {
        let statusResponse: ClientShopifyThemeTemplatePublishJobStatusResponse;
        try {
          statusResponse = await get<ClientShopifyThemeTemplatePublishJobStatusResponse>(
            `/clients/${clientId}/shopify/theme/brand/template/publish-jobs/${publishJobId}`,
          );
          consecutiveTransientFailures = 0;
        } catch (err) {
          const statusCode =
            typeof err === "object" && err !== null && "status" in err
              ? (err as { status?: unknown }).status
              : undefined;
          const isTransientFailure =
            statusCode === 0 ||
            statusCode === 502 ||
            statusCode === 503 ||
            statusCode === 504;
          if (!isTransientFailure) {
            throw err;
          }
          consecutiveTransientFailures += 1;
          if (Date.now() - startedAt > pollTimeoutMs) {
            throw new Error("Timed out waiting for Shopify template publish to complete.");
          }
          if (consecutiveTransientFailures >= maxConsecutiveTransientFailures) {
            throw new Error(
              "Unable to reach publish status endpoint after multiple attempts. " +
                "The publish job may still be running; refresh and check draft publish status.",
            );
          }
          const retryDelayMs = Math.min(10000, pollIntervalMs * consecutiveTransientFailures);
          await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
          continue;
        }
        if (statusResponse.status === "succeeded") {
          if (statusResponse.result) return statusResponse.result;
          throw new Error("Shopify template publish completed but no result payload was returned.");
        }
        if (statusResponse.status === "failed") {
          const errorMessage = statusResponse.error?.trim();
          throw new Error(errorMessage || "Shopify template publish failed.");
        }
        if (Date.now() - startedAt > pollTimeoutMs) {
          throw new Error("Timed out waiting for Shopify template publish to complete.");
        }
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      }
    },
    onSuccess: (response) => {
      toast.success(
        `Published template draft v${response.version.versionNumber} to ${response.sync.themeName}`,
      );
      queryClient.invalidateQueries({
        queryKey: ["clients", "shopify-theme-template-drafts", clientId],
      });
    },
    onError: (err: ApiError | Error) => {
      const message =
        "message" in err ? err.message : err?.message || "Failed to publish Shopify template draft";
      toast.error(message);
    },
  });
}

function parseFilenameFromContentDisposition(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null;
  const filenameMatch = contentDisposition.match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i);
  if (!filenameMatch?.[1]) return null;
  try {
    return decodeURIComponent(filenameMatch[1].trim().replace(/^\"|\"$/g, ""));
  } catch {
    return filenameMatch[1].trim().replace(/^\"|\"$/g, "");
  }
}

function isZipContentType(contentType: string | null): boolean {
  if (!contentType) return false;
  const normalized = contentType.toLowerCase();
  return (
    normalized.includes("application/zip") ||
    normalized.includes("application/x-zip-compressed") ||
    normalized.includes("application/octet-stream")
  );
}

async function parseDownloadError(resp: Response): Promise<Error> {
  try {
    const raw = await resp.clone().json();
    const detail = (raw as { detail?: unknown })?.detail;
    if (typeof detail === "string" && detail.trim()) return new Error(detail);
    const message = (raw as { message?: unknown })?.message;
    if (typeof message === "string" && message.trim()) return new Error(message);
  } catch {
    // Fall through to text parsing.
  }
  const text = (await resp.text()).trim();
  if (text) return new Error(text);
  return new Error(resp.statusText || "Failed to download Shopify template ZIP");
}

export function useDownloadClientShopifyThemeTemplateZip(clientId?: string) {
  const { getToken } = useAuth();

  return useMutation({
    mutationFn: async (payload: ClientShopifyThemeTemplatePublishPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      if (!payload.draftId?.trim()) throw new Error("Draft ID is required.");
      const token = await getToken({ template: clerkTokenTemplate });
      const headers = new Headers({ "Content-Type": "application/json" });
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const response = await fetch(
        `${defaultBaseUrl}/clients/${clientId}/shopify/theme/brand/template/export-zip`,
        {
          method: "POST",
          headers,
          body: JSON.stringify(payload),
        },
      );
      if (!response.ok) {
        throw await parseDownloadError(response);
      }
      const responseContentType = response.headers.get("Content-Type");
      if (!isZipContentType(responseContentType)) {
        const preview = (await response.text()).trim().slice(0, 240);
        const contentTypeLabel = responseContentType?.trim() || "unknown content type";
        throw new Error(
          preview
            ? `Expected a ZIP download but received ${contentTypeLabel}. Response preview: ${preview}`
            : `Expected a ZIP download but received ${contentTypeLabel}.`,
        );
      }
      const blob = await response.blob();
      const fileNameFromHeader = parseFilenameFromContentDisposition(
        response.headers.get("Content-Disposition"),
      );
      const filename = fileNameFromHeader || `shopify-template-${payload.draftId}.zip`;
      return { blob, filename };
    },
    onSuccess: ({ blob, filename }) => {
      const downloadUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(downloadUrl);
      toast.success(`Downloaded ${filename}`);
    },
    onError: (err: ApiError | Error) => {
      const message =
        "message" in err ? err.message : err?.message || "Failed to download Shopify template ZIP";
      toast.error(message);
    },
  });
}

export function useGenerateClientShopifyThemeTemplateImages(clientId?: string) {
  const { get, post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: ClientShopifyThemeTemplateGenerateImagesPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      if (!payload.draftId?.trim()) throw new Error("Draft ID is required.");
      const startResponse = await post<ClientShopifyThemeTemplateGenerateImagesJobStartResponse>(
        `/clients/${clientId}/shopify/theme/brand/template/generate-images-async`,
        payload,
      );
      const generationJobId = startResponse.jobId;
      if (!generationJobId || !generationJobId.trim()) {
        throw new Error("Shopify template image generation job was not started.");
      }

      const pollTimeoutMs = 1000 * 60 * 90;
      const pollIntervalMs = 2000;
      const startedAt = Date.now();

      while (true) {
        const statusResponse = await get<ClientShopifyThemeTemplateGenerateImagesJobStatusResponse>(
          `/clients/${clientId}/shopify/theme/brand/template/generate-images-jobs/${generationJobId}`,
        );
        if (statusResponse.status === "succeeded") {
          if (statusResponse.result) return statusResponse.result;
          throw new Error("Template image generation completed but no result payload was returned.");
        }
        if (statusResponse.status === "failed") {
          const errorMessage = statusResponse.error?.trim();
          throw new Error(errorMessage || "Shopify template image generation failed.");
        }
        if (Date.now() - startedAt > pollTimeoutMs) {
          throw new Error("Timed out waiting for template image generation to complete.");
        }
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      }
    },
    onSuccess: (response) => {
      const nonFatalErrors = [
        response.imageGenerationError?.trim(),
        response.copyGenerationError?.trim(),
      ].filter((message): message is string => Boolean(message));
      const textSummary =
        response.generatedTextCount > 0
          ? ` Refreshed ${response.generatedTextCount} text slot(s).`
          : "";
      if (response.generatedImageCount > 0 || response.generatedTextCount > 0) {
        if (response.remainingSlotPaths.length) {
          toast.success(
            `Generated ${response.generatedImageCount} template image(s). ` +
              `${response.remainingSlotPaths.length} slot(s) still pending.` +
              textSummary,
          );
        } else {
          toast.success(
            `Generated ${response.generatedImageCount} template image(s).` + textSummary,
          );
        }
      } else {
        toast.success("No new template assets were generated.");
      }
      if (nonFatalErrors.length) {
        toast.error(nonFatalErrors.join(" "));
      }
      queryClient.invalidateQueries({
        queryKey: ["clients", "shopify-theme-template-drafts", clientId],
      });
    },
    onError: (err: ApiError | Error) => {
      const message =
        "message" in err ? err.message : err?.message || "Failed to generate Shopify template images";
      toast.error(message);
    },
  });
}

export function useAuditClientShopifyThemeBrand(clientId?: string) {
  const { post } = useApiClient();

  return useMutation({
    mutationFn: (payload: ClientShopifyThemeBrandSyncPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<ClientShopifyThemeBrandAuditResponse>(
        `/clients/${clientId}/shopify/theme/brand/audit`,
        payload,
      );
    },
    onSuccess: (response) => {
      const status = response.isReady ? "ready" : "has gaps";
      toast.success(`Shopify theme audit completed (${status}) for ${response.shopDomain}`);
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to audit Shopify theme brand";
      toast.error(message);
    },
  });
}

export function useCreateClient() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { name: string; industry?: string; strategyV2Enabled?: boolean }) =>
      post<Client>("/clients", payload),
    onSuccess: () => {
      toast.success("Client created");
      queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create client";
      toast.error(message);
    },
  });
}

export function useUpdateClient() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ clientId, payload }: { clientId: string; payload: Record<string, unknown> }) =>
      request<Client>(`/clients/${clientId}`, { method: "PATCH", body: JSON.stringify(payload) }),
    onSuccess: (_data, vars) => {
      toast.success("Client updated");
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      queryClient.invalidateQueries({ queryKey: ["clients", vars.clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update client";
      toast.error(message);
    },
  });
}

export function useStartOnboarding() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ clientId, payload }: { clientId: string; payload: Record<string, unknown> }) =>
      post<{
        workflow_run_id: string;
        temporal_workflow_id: string;
        product_id: string;
        product_name?: string;
        default_offer_id?: string;
      }>(`/clients/${clientId}/onboarding`, payload),
    onSuccess: () => {
      toast.success("Onboarding started");
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to start onboarding";
      toast.error(message);
    },
  });
}

export function useDeleteClient() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ clientId, confirmName }: { clientId: string; confirmName: string }) =>
      request(`/clients/${clientId}`, {
        method: "DELETE",
        body: JSON.stringify({ confirm: true, confirm_name: confirmName }),
      }),
    onSuccess: () => {
      toast.success("Workspace deleted");
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to delete workspace";
      toast.error(message);
    },
  });
}
