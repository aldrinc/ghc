import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import type { Client } from "@/types/common";
import { toast } from "@/components/ui/toast";

export type ShopifyConnectionState =
  | "not_connected"
  | "installed_missing_storefront_token"
  | "multiple_installations_conflict"
  | "ready"
  | "error";

export type ClientShopifyStatus = {
  state: ShopifyConnectionState;
  message: string;
  shopDomain?: string | null;
  shopDomains: string[];
  selectedShopDomain?: string | null;
  hasStorefrontAccessToken: boolean;
  missingScopes: string[];
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
  shopDomain?: string;
  themeId?: string;
  themeName?: string;
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
  jobId: string;
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

export function useCreateClientShopifyInstallUrl(clientId: string) {
  const { post } = useApiClient();

  return useMutation({
    mutationFn: (payload: { shopDomain: string }) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<{ installUrl: string }>(`/clients/${clientId}/shopify/install-url`, payload);
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
  const { post } = useApiClient();

  return useMutation({
    mutationFn: (payload: ClientShopifyThemeBrandSyncPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<ClientShopifyThemeBrandSyncResponse>(
        `/clients/${clientId}/shopify/theme/brand/sync`,
        payload,
      );
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

export function useCreateClient() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { name: string; industry?: string }) => post<Client>("/clients", payload),
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
