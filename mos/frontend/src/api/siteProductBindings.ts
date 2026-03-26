import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient } from "@/api/client";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export interface SiteProductPageBinding {
  id: string;
  siteId: string;
  productId: string;
  sitePageId: string;
  pageRole: string;
  siteFunnelId: string | null;
  priority: number;
  active: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface SiteProductBindingDetail extends SiteProductPageBinding {
  site: {
    id: string;
    name: string;
    routeSlug: string | null;
  };
  page: {
    id: string;
    name: string;
    slug: string;
    pageType: string | null;
  };
  funnel?: {
    id: string;
    name: string;
  } | null;
}

export interface CreateSiteProductBindingRequest {
  siteId: string;
  productId: string;
  sitePageId: string;
  pageRole?: string;
  siteFunnelId?: string;
  priority?: number;
}

export interface UpdateSiteProductBindingRequest {
  sitePageId?: string;
  pageRole?: string;
  siteFunnelId?: string | null;
  priority?: number;
  active?: boolean;
}

// Get all product bindings for a site
export function useSiteProductBindings(siteId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SiteProductBindingDetail[]>({
    queryKey: ["sites", siteId, "product-bindings"],
    queryFn: () => get<SiteProductBindingDetail[]>(`/sites/${siteId}/product-bindings?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!siteId,
  });
}

// Get product bindings for a specific product across all sites
export function useProductSiteBindings(productId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SiteProductBindingDetail[]>({
    queryKey: ["products", productId, "site-bindings"],
    queryFn: () => get<SiteProductBindingDetail[]>(`/products/${productId}/site-bindings?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!productId,
  });
}

// Create a new product binding
export function useCreateSiteProductBinding(siteId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: Omit<CreateSiteProductBindingRequest, "siteId">) =>
      post<SiteProductPageBinding>(`/sites/${siteId}/product-bindings?clientId=${workspace!.id}`, {
        ...request,
        siteId: siteId!,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "product-bindings"] });
    },
  });
}

// Update a product binding
export function useUpdateSiteProductBinding(siteId: string | null | undefined, bindingId: string | null | undefined) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (payload: UpdateSiteProductBindingRequest) =>
      request<SiteProductPageBinding>(`/sites/${siteId}/product-bindings/${bindingId}?clientId=${workspace!.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "product-bindings"] });
    },
  });
}

// Delete a product binding
export function useDeleteSiteProductBinding(siteId: string | null | undefined) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (bindingId: string) =>
      request<void>(`/sites/${siteId}/product-bindings/${bindingId}?clientId=${workspace!.id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "product-bindings"] });
    },
  });
}

// Get sites that use a specific product
export function useProductSites(productId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<{ siteId: string; siteName: string; hasBinding: boolean }[]>({
    queryKey: ["products", productId, "sites"],
    queryFn: () => get<{ siteId: string; siteName: string; hasBinding: boolean }[]>(`/products/${productId}/sites?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!productId,
  });
}
