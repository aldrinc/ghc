import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { toast } from "@/components/ui/toast";

function getMutationErrorMessage(err: ApiError | Error, fallback: string): string {
  const candidate = err as { message?: unknown };
  return typeof candidate.message === "string" && candidate.message ? candidate.message : fallback;
}

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

type SiteProductBindingQueryOptions = {
  clientId?: string | null;
};

// Get all product bindings for a site
export function useSiteProductBindings(
  siteId: string | null | undefined,
  options: SiteProductBindingQueryOptions = {},
) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  const clientId = Object.prototype.hasOwnProperty.call(options, "clientId")
    ? options.clientId ?? null
    : workspace?.id ?? null;
  return useQuery<SiteProductBindingDetail[]>({
    queryKey: ["sites", siteId, "product-bindings", clientId ?? "__missing_client__"],
    queryFn: () => get<SiteProductBindingDetail[]>(`/sites/${siteId}/product-bindings?clientId=${clientId}`),
    enabled: !!clientId && !!siteId,
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
      post<SiteProductBindingDetail>(`/sites/${siteId}/product-bindings?clientId=${workspace!.id}`, {
        ...request,
        siteId: siteId!,
      }),
    onSuccess: (_binding, variables) => {
      toast.success("Product binding created");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "product-bindings"] });
      queryClient.invalidateQueries({ queryKey: ["products", variables.productId, "site-bindings"] });
      queryClient.invalidateQueries({ queryKey: ["products", variables.productId, "sites"] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to create product binding"));
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
      request<SiteProductBindingDetail>(`/sites/${siteId}/product-bindings/${bindingId}?clientId=${workspace!.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      toast.success("Product binding updated");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "product-bindings"] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to update product binding"));
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
      toast.success("Product binding removed");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "product-bindings"] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to remove product binding"));
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
