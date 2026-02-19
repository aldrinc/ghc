import { useAuth } from "@clerk/clerk-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type {
  Product,
  ProductAsset,
  ProductDetail,
  ProductOffer,
  ProductOfferBonus,
  ProductVariant,
} from "@/types/products";

type ShopifyCreatedVariant = {
  variantGid: string;
  title: string;
  priceCents: number;
  currency: string;
};

type ShopifyCreateProductResponse = {
  shopDomain: string;
  productGid: string;
  title: string;
  handle: string;
  status: string;
  variants: ShopifyCreatedVariant[];
};

type ShopifyCatalogVariant = {
  variantGid: string;
  title: string;
  priceCents: number;
  currency: string;
  compareAtPriceCents?: number | null;
  sku?: string | null;
  barcode?: string | null;
  taxable: boolean;
  requiresShipping: boolean;
  inventoryPolicy?: string | null;
  inventoryManagement?: string | null;
  inventoryQuantity?: number | null;
  optionValues: Record<string, string>;
};

type ShopifyVariantSyncResponse = {
  shopDomain: string;
  productGid: string;
  createdCount: number;
  updatedCount: number;
  totalFetched: number;
  variants: ShopifyCatalogVariant[];
};

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
      title: string;
      description?: string;
      productType?: string;
      shopifyProductGid?: string;
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
      title?: string;
      description?: string | null;
      productType?: string | null;
      shopifyProductGid?: string | null;
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

export function useCreateVariant(productId: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      title: string;
      price: number;
      currency: string;
      offerId?: string;
      compareAtPrice?: number;
      provider?: string;
      externalPriceId?: string;
      optionValues?: Record<string, unknown>;
      sku?: string;
      barcode?: string;
      requiresShipping?: boolean;
      taxable?: boolean;
      weight?: number;
      weightUnit?: string;
      inventoryQuantity?: number;
      inventoryPolicy?: string;
      inventoryManagement?: string;
      incoming?: boolean;
      nextIncomingDate?: string;
      unitPrice?: number;
      unitPriceMeasurement?: Record<string, unknown>;
      quantityRule?: Record<string, unknown>;
      quantityPriceBreaks?: Record<string, unknown>[];
    }) => post<ProductVariant>(`/products/${productId}/variants`, payload),
    onSuccess: () => {
      toast.success("Variant created");
      queryClient.invalidateQueries({ queryKey: ["products", "detail", productId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create variant";
      toast.error(message);
    },
  });
}

export function useCreateShopifyProductForProduct(productId: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      title: string;
      description?: string;
      handle?: string;
      vendor?: string;
      productType?: string;
      tags?: string[];
      status?: "ACTIVE" | "DRAFT";
      variants: Array<{ title: string; priceCents: number; currency: string }>;
      shopDomain?: string;
    }) =>
      post<ShopifyCreateProductResponse>(`/products/${productId}/shopify/create`, payload),
    onSuccess: () => {
      toast.success("Shopify product created and variants imported");
      queryClient.invalidateQueries({ queryKey: ["products", "detail", productId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create Shopify product";
      toast.error(message);
    },
  });
}

export function useSyncShopifyVariantsForProduct(productId: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload?: { shopDomain?: string }) =>
      post<ShopifyVariantSyncResponse>(`/products/${productId}/shopify/sync-variants`, payload || {}),
    onSuccess: (response) => {
      toast.success(
        `Shopify variants synced (${response.createdCount} created, ${response.updatedCount} updated)`,
      );
      queryClient.invalidateQueries({ queryKey: ["products", "detail", productId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to sync Shopify variants";
      toast.error(message);
    },
  });
}

export function useProductOffers(productId?: string) {
  const { get } = useApiClient();
  return useQuery<ProductOffer[]>({
    queryKey: ["products", "offers", productId],
    queryFn: () => get(`/products/${productId}/offers`),
    enabled: Boolean(productId),
  });
}

export function useCreateProductOffer(productId: string) {
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
    }) => post<ProductOffer>(`/products/${productId}/offers`, payload),
    onSuccess: () => {
      toast.success("Offer created");
      queryClient.invalidateQueries({ queryKey: ["products", "detail", productId] });
      queryClient.invalidateQueries({ queryKey: ["products", "offers", productId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to create offer";
      toast.error(message);
    },
  });
}

export function useUpdateProductOffer(offerId: string, productIdForInvalidation?: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      name?: string;
      description?: string | null;
      businessModel?: string | null;
      differentiationBullets?: string[] | null;
      guaranteeText?: string | null;
      optionsSchema?: Record<string, unknown> | null;
    }) =>
      request<ProductOffer>(`/products/offers/${offerId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      toast.success("Offer updated");
      if (productIdForInvalidation) {
        queryClient.invalidateQueries({ queryKey: ["products", "detail", productIdForInvalidation] });
        queryClient.invalidateQueries({ queryKey: ["products", "offers", productIdForInvalidation] });
      }
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update offer";
      toast.error(message);
    },
  });
}

export function useAddOfferBonus(productIdForInvalidation?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { offerId: string; bonusProductId: string }) =>
      post<ProductOfferBonus>(`/products/offers/${payload.offerId}/bonuses`, {
        bonusProductId: payload.bonusProductId,
      }),
    onSuccess: () => {
      toast.success("Bonus added");
      if (productIdForInvalidation) {
        queryClient.invalidateQueries({ queryKey: ["products", "detail", productIdForInvalidation] });
        queryClient.invalidateQueries({ queryKey: ["products", "offers", productIdForInvalidation] });
      }
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to add bonus";
      toast.error(message);
    },
  });
}

export function useRemoveOfferBonus(productIdForInvalidation?: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { offerId: string; bonusProductId: string }) =>
      request<{ ok: boolean }>(`/products/offers/${payload.offerId}/bonuses/${payload.bonusProductId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success("Bonus removed");
      if (productIdForInvalidation) {
        queryClient.invalidateQueries({ queryKey: ["products", "detail", productIdForInvalidation] });
        queryClient.invalidateQueries({ queryKey: ["products", "offers", productIdForInvalidation] });
      }
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to remove bonus";
      toast.error(message);
    },
  });
}

export function useUpdateVariant(variantId: string, productIdForInvalidation?: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      title?: string;
      price?: number;
      currency?: string;
      offerId?: string | null;
      compareAtPrice?: number | null;
      provider?: string | null;
      externalPriceId?: string | null;
      optionValues?: Record<string, unknown> | null;
      sku?: string | null;
      barcode?: string | null;
      requiresShipping?: boolean | null;
      taxable?: boolean | null;
      weight?: number | null;
      weightUnit?: string | null;
      inventoryQuantity?: number | null;
      inventoryPolicy?: string | null;
      inventoryManagement?: string | null;
      incoming?: boolean | null;
      nextIncomingDate?: string | null;
      unitPrice?: number | null;
      unitPriceMeasurement?: Record<string, unknown> | null;
      quantityRule?: Record<string, unknown> | null;
      quantityPriceBreaks?: Record<string, unknown>[] | null;
    }) =>
      request<ProductVariant>(`/products/variants/${variantId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      toast.success("Variant updated");
      if (productIdForInvalidation) {
        queryClient.invalidateQueries({ queryKey: ["products", "detail", productIdForInvalidation] });
      }
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update variant";
      toast.error(message);
    },
  });
}
