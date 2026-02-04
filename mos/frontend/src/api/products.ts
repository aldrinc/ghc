import { useAuth } from "@clerk/clerk-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type { Product, ProductAsset, ProductDetail, ProductOffer, ProductOfferPricePoint } from "@/types/products";

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";
const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";

async function readUploadError(resp: Response): Promise<string> {
  try {
    const raw = await resp.clone().json();
    const detail = (raw as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined;
      if (typeof first?.msg === "string") return first.msg;
    }
    if (typeof (raw as { message?: unknown })?.message === "string") {
      return (raw as { message?: string }).message || "Upload failed";
    }
  } catch {
    // Fall through to text parsing
  }
  try {
    const text = await resp.text();
    if (text) return text;
  } catch {
    // Fall through to status text
  }
  return resp.statusText || "Upload failed";
}

export function useProducts(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<Product[]>({
    queryKey: ["products", "list", clientId],
    queryFn: () => {
      const query = clientId ? `?clientId=${encodeURIComponent(clientId)}` : "";
      return get(`/products${query}`);
    },
    enabled: Boolean(clientId),
  });
}

export function useCreateProduct() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      clientId: string;
      name: string;
      description?: string;
      category?: string;
      primaryBenefits?: string[];
      featureBullets?: string[];
      guaranteeText?: string;
      disclaimers?: string[];
    }) => post<Product>("/products", payload),
    onSuccess: (product) => {
      toast.success("Product created");
      queryClient.invalidateQueries({ queryKey: ["products", "list", product.client_id] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create product";
      toast.error(message);
    },
  });
}

export function useUpdateProduct(productId: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      name?: string;
      description?: string | null;
      category?: string | null;
      primaryBenefits?: string[] | null;
      featureBullets?: string[] | null;
      guaranteeText?: string | null;
      disclaimers?: string[] | null;
      primaryAssetId?: string | null;
    }) =>
      request<Product>(`/products/${productId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: (product) => {
      toast.success("Product updated");
      queryClient.invalidateQueries({ queryKey: ["products", "list", product.client_id] });
      queryClient.invalidateQueries({ queryKey: ["products", "detail", product.id] });
      queryClient.invalidateQueries({ queryKey: ["products", "assets", product.id] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update product";
      toast.error(message);
    },
  });
}

export function useProduct(productId?: string) {
  const { get } = useApiClient();
  return useQuery<ProductDetail>({
    queryKey: ["products", "detail", productId],
    queryFn: () => get(`/products/${productId}`),
    enabled: Boolean(productId),
  });
}

export function useProductAssets(productId?: string) {
  const { get } = useApiClient();
  return useQuery<ProductAsset[]>({
    queryKey: ["products", "assets", productId],
    queryFn: () => get(`/products/${productId}/assets`),
    enabled: Boolean(productId),
  });
}

export function useUploadProductAssets(productId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (files: File[]) => {
      if (!productId) throw new Error("Product ID is required to upload assets.");
      if (!files.length) throw new Error("No files selected for upload.");

      const token = await getToken({ template: clerkTokenTemplate, skipCache: true });
      const formData = new FormData();
      files.forEach((file) => formData.append("files", file));

      const resp = await fetch(`${defaultBaseUrl}/products/${productId}/assets`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      });
      if (!resp.ok) {
        const message = await readUploadError(resp);
        throw new Error(message);
      }
      const data = (await resp.json()) as { assets?: ProductAsset[] };
      if (!data.assets || !Array.isArray(data.assets)) {
        throw new Error("Upload succeeded but response is missing assets.");
      }
      return data.assets;
    },
    onSuccess: () => {
      toast.success("Assets uploaded");
      queryClient.invalidateQueries({ queryKey: ["products", "assets", productId] });
      queryClient.invalidateQueries({ queryKey: ["products", "detail", productId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to upload assets";
      toast.error(message);
    },
  });
}

export function useCreateOffer() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      productId: string;
      name: string;
      description?: string;
      businessModel: string;
      differentiationBullets?: string[];
      guaranteeText?: string;
      optionsSchema?: Record<string, unknown>;
    }) => post<ProductOffer>(`/products/${payload.productId}/offers`, payload),
    onSuccess: (offer) => {
      toast.success("Offer created");
      queryClient.invalidateQueries({ queryKey: ["products", "detail", offer.product_id] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create offer";
      toast.error(message);
    },
  });
}

export function useCreatePricePoint() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      offerId: string;
      label: string;
      amountCents: number;
      currency: string;
      provider?: string;
      externalPriceId?: string;
      optionValues?: Record<string, unknown>;
      productId: string;
    }) =>
      post<ProductOfferPricePoint>(`/products/offers/${payload.offerId}/price-points`, {
        offerId: payload.offerId,
        label: payload.label,
        amountCents: payload.amountCents,
        currency: payload.currency,
        provider: payload.provider,
        externalPriceId: payload.externalPriceId,
        optionValues: payload.optionValues,
      }),
    onSuccess: (_pricePoint, variables) => {
      toast.success("Price point created");
      queryClient.invalidateQueries({ queryKey: ["products", "detail", variables.productId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create price point";
      toast.error(message);
    },
  });
}
