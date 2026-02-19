import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle, DialogClose } from "@/components/ui/dialog";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import {
  useClientShopifyStatus,
  useCreateClientShopifyInstallUrl,
  useDisconnectClientShopifyInstallation,
  useListClientShopifyProducts,
  useSetClientShopifyDefaultShop,
  useUpdateClientShopifyInstallation,
} from "@/api/clients";
import {
  useAddOfferBonus,
  useCreateProductOffer,
  useCreateShopifyProductForProduct,
  useCreateVariant,
  useProduct,
  useProductAssets,
  useRemoveOfferBonus,
  useUpdateProduct,
  useUploadProductAssets,
} from "@/api/products";
import { toast } from "@/components/ui/toast";
import type { ProductAsset } from "@/types/products";

function formatBytes(value?: number | null): string | null {
  if (value === null || value === undefined) return null;
  if (value === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(size < 10 && idx > 0 ? 1 : 0)} ${units[idx]}`;
}

function assetLabel(asset: ProductAsset): string {
  const filename = asset.ai_metadata?.filename;
  if (typeof filename === "string" && filename.trim()) return filename;
  if (asset.content_type) return asset.content_type;
  return `Asset ${asset.id.slice(0, 8)}`;
}

export function ProductDetailPage() {
  const { productId } = useParams();
  const { workspace } = useWorkspace();
  const { products, selectProduct } = useProductContext();
  const navigate = useNavigate();

  const { data: productDetail, isLoading: isLoadingDetail } = useProduct(productId);
  const { data: productAssets = [], isLoading: isLoadingAssets } = useProductAssets(productId);
  const productClientId = productDetail?.client_id;
  const {
    data: shopifyStatus,
    isLoading: isLoadingShopifyStatus,
    refetch: refetchShopifyStatus,
    error: shopifyStatusError,
  } = useClientShopifyStatus(productClientId);
  const createShopifyInstallUrl = useCreateClientShopifyInstallUrl(productClientId || "");
  const listShopifyProducts = useListClientShopifyProducts(productClientId || "");
  const setDefaultShop = useSetClientShopifyDefaultShop(productClientId || "");
  const updateShopifyInstallation = useUpdateClientShopifyInstallation(productClientId || "");
  const disconnectShopifyInstallation = useDisconnectClientShopifyInstallation(productClientId || "");
  const updateProduct = useUpdateProduct(productId || "");
  const createShopifyProductForProduct = useCreateShopifyProductForProduct(productId || "");
  const createOffer = useCreateProductOffer(productId || "");
  const addOfferBonus = useAddOfferBonus(productId || "");
  const removeOfferBonus = useRemoveOfferBonus(productId || "");
  const uploadProductAssets = useUploadProductAssets(productId || "");
  const assetInputRef = useRef<HTMLInputElement | null>(null);

  const createVariant = useCreateVariant(productId || "");
  const [isVariantModalOpen, setIsVariantModalOpen] = useState(false);
  const [isOfferModalOpen, setIsOfferModalOpen] = useState(false);

  const [variantTitle, setVariantTitle] = useState("");
  const [variantPrice, setVariantPrice] = useState("");
  const [variantCurrency, setVariantCurrency] = useState("usd");
  const [variantOfferId, setVariantOfferId] = useState("");
  const [variantProvider, setVariantProvider] = useState("stripe");
  const [variantExternalId, setVariantExternalId] = useState("");
  const [variantOptionValues, setVariantOptionValues] = useState("");
  const [shopifyProductGidDraft, setShopifyProductGidDraft] = useState("");
  const [shopifyShopDomainDraft, setShopifyShopDomainDraft] = useState("");
  const [defaultShopDomainDraft, setDefaultShopDomainDraft] = useState("");
  const [storefrontAccessTokenDraft, setStorefrontAccessTokenDraft] = useState("");
  const [shopifyProductSearchQuery, setShopifyProductSearchQuery] = useState("");
  const [selectedShopifyProductGid, setSelectedShopifyProductGid] = useState("");
  const [createShopifyTitleDraft, setCreateShopifyTitleDraft] = useState("");
  const [createShopifyVariantTitleDraft, setCreateShopifyVariantTitleDraft] = useState("Default");
  const [createShopifyVariantPriceDraft, setCreateShopifyVariantPriceDraft] = useState("");
  const [createShopifyCurrencyDraft, setCreateShopifyCurrencyDraft] = useState("USD");
  const [shopifyImportSummary, setShopifyImportSummary] = useState<{
    shopDomain: string;
    productGid: string;
    variantTitles: string[];
    variantCount: number;
  } | null>(null);
  const [offerName, setOfferName] = useState("");
  const [offerBusinessModel, setOfferBusinessModel] = useState("one_time");
  const [offerDescription, setOfferDescription] = useState("");
  const [bonusSelectionByOffer, setBonusSelectionByOffer] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!productDetail) return;
    selectProduct(productDetail.id, {
      title: productDetail.title,
      client_id: productDetail.client_id,
      product_type: productDetail.product_type ?? null,
    });
    setShopifyProductGidDraft(productDetail.shopify_product_gid || "");
  }, [productDetail, selectProduct]);

  useEffect(() => {
    if (!shopifyStatus?.shopDomain) return;
    setShopifyShopDomainDraft((current) => (current.trim() ? current : shopifyStatus.shopDomain || ""));
  }, [shopifyStatus?.shopDomain]);

  useEffect(() => {
    if (!shopifyStatus?.shopDomains?.length) return;
    setDefaultShopDomainDraft((current) => {
      if (current.trim()) return current;
      if (shopifyStatus.selectedShopDomain) return shopifyStatus.selectedShopDomain;
      return shopifyStatus.shopDomains[0] || "";
    });
  }, [shopifyStatus?.selectedShopDomain, shopifyStatus?.shopDomains]);

  useEffect(() => {
    if (!productDetail) return;
    setCreateShopifyTitleDraft((current) => (current.trim() ? current : productDetail.title || ""));
  }, [productDetail]);

  useEffect(() => {
    setShopifyImportSummary(null);
  }, [productId]);

  const resetVariantForm = () => {
    setVariantTitle("");
    setVariantPrice("");
    setVariantCurrency("usd");
    setVariantOfferId("");
    setVariantProvider("stripe");
    setVariantExternalId("");
    setVariantOptionValues("");
  };

  const resetOfferForm = () => {
    setOfferName("");
    setOfferBusinessModel("one_time");
    setOfferDescription("");
  };

  const handleCreateVariant = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!workspace || !productId) return;
    const price = Number(variantPrice);
    if (!variantTitle.trim() || Number.isNaN(price) || price <= 0) {
      toast.error("Variant title and price are required.");
      return;
    }
    if (!variantCurrency.trim()) {
      toast.error("Currency is required.");
      return;
    }
    if (variantExternalId.trim() && !variantProvider.trim()) {
      toast.error("Provider is required when external price ID is set.");
      return;
    }
    let optionValues: Record<string, unknown> | undefined;
    if (variantOptionValues.trim()) {
      try {
        const parsed = JSON.parse(variantOptionValues);
        if (!parsed || typeof parsed !== "object") {
          throw new Error("Option values must be a JSON object.");
        }
        optionValues = parsed as Record<string, unknown>;
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Invalid option values JSON.");
        return;
      }
    }
    await createVariant.mutateAsync({
      title: variantTitle.trim(),
      price,
      currency: variantCurrency.trim(),
      offerId: variantOfferId.trim() || undefined,
      provider: variantProvider.trim() || undefined,
      externalPriceId: variantExternalId.trim() || undefined,
      optionValues,
    });
    resetVariantForm();
    setIsVariantModalOpen(false);
  };

  const handleAssetUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!productId) {
      toast.error("Select a product before uploading assets.");
      event.target.value = "";
      return;
    }
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      toast.error("No files selected.");
      event.target.value = "";
      return;
    }
    try {
      await uploadProductAssets.mutateAsync(files);
    } finally {
      event.target.value = "";
    }
  };

  const handleSetPrimary = (assetId: string | null) => {
    if (!productId) {
      toast.error("Select a product before setting a primary image.");
      return;
    }
    updateProduct.mutate({ primaryAssetId: assetId });
  };

  const handleSaveShopifyProductGid = () => {
    if (!productDetail) return;
    if (shopifyStatus?.state !== "ready") {
      toast.error("Shopify must be connected and ready before mapping products.");
      return;
    }
    const next = shopifyProductGidDraft.trim();
    updateProduct.mutate({ shopifyProductGid: next || null });
  };

  const handleConnectShopify = async () => {
    if (!productClientId) {
      toast.error("Select a product before connecting Shopify.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    const response = await createShopifyInstallUrl.mutateAsync({ shopDomain: nextDomain });
    if (!response.installUrl) {
      throw new Error("Install URL is missing from response.");
    }
    window.location.assign(response.installUrl);
  };

  const handleSetStorefrontToken = async () => {
    if (!productClientId) {
      toast.error("Select a product before updating Shopify installation.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    const nextToken = storefrontAccessTokenDraft.trim();
    if (!nextToken) {
      toast.error("Storefront access token is required.");
      return;
    }
    await updateShopifyInstallation.mutateAsync({
      shopDomain: nextDomain,
      storefrontAccessToken: nextToken,
    });
    setStorefrontAccessTokenDraft("");
    await refetchShopifyStatus();
  };

  const handleSetDefaultShop = async () => {
    if (!productClientId) {
      toast.error("Select a product before setting default Shopify store.");
      return;
    }
    const nextDomain = defaultShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Select a Shopify shop domain.");
      return;
    }
    await setDefaultShop.mutateAsync({ shopDomain: nextDomain });
    await refetchShopifyStatus();
  };

  const handleDisconnectShopify = async () => {
    if (!productClientId) {
      toast.error("Select a product before disconnecting Shopify.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    await disconnectShopifyInstallation.mutateAsync({ shopDomain: nextDomain });
    setStorefrontAccessTokenDraft("");
    await refetchShopifyStatus();
  };

  const handleCreateShopifyProduct = async () => {
    if (!isShopifyReady) {
      toast.error("Shopify must be connected and ready before creating products.");
      return;
    }
    if (!productDetail) return;
    const nextTitle = createShopifyTitleDraft.trim();
    if (!nextTitle) {
      toast.error("Shopify product title is required.");
      return;
    }
    const nextVariantTitle = createShopifyVariantTitleDraft.trim();
    if (!nextVariantTitle) {
      toast.error("Shopify variant title is required.");
      return;
    }
    const nextVariantPrice = Number(createShopifyVariantPriceDraft);
    if (Number.isNaN(nextVariantPrice) || nextVariantPrice <= 0) {
      toast.error("Shopify variant price must be greater than 0.");
      return;
    }
    const nextCurrency = createShopifyCurrencyDraft.trim().toUpperCase();
    if (nextCurrency.length !== 3) {
      toast.error("Currency must be a 3-letter code.");
      return;
    }

    const response = await createShopifyProductForProduct.mutateAsync({
      title: nextTitle,
      description: productDetail.description || undefined,
      handle: productDetail.handle || undefined,
      vendor: productDetail.vendor || undefined,
      productType: productDetail.product_type || undefined,
      tags: productDetail.tags || [],
      status: "DRAFT",
      variants: [
        {
          title: nextVariantTitle,
          priceCents: Math.round(nextVariantPrice * 100),
          currency: nextCurrency,
        },
      ],
      shopDomain: shopifyStatus?.shopDomain || undefined,
    });
    const createdProductGid = String(response.productGid || "").trim();
    if (createdProductGid) {
      setShopifyProductGidDraft(createdProductGid);
    }
    const importedVariantTitles = (response.variants || [])
      .map((variant) => String(variant.title || "").trim())
      .filter((title) => Boolean(title));
    setShopifyImportSummary({
      shopDomain: response.shopDomain,
      productGid: createdProductGid || response.productGid,
      variantTitles: importedVariantTitles,
      variantCount: importedVariantTitles.length,
    });
  };

  const handleSearchShopifyProducts = async () => {
    if (!productClientId) {
      toast.error("Select a product before searching Shopify products.");
      return;
    }
    if (!isShopifyReady) {
      toast.error("Shopify must be connected and ready before searching products.");
      return;
    }
    const response = await listShopifyProducts.mutateAsync({
      query: shopifyProductSearchQuery.trim() || undefined,
      shopDomain: shopifyStatus?.shopDomain || undefined,
      limit: 25,
    });
    if (!response.products.length) {
      toast.error("No Shopify products matched your search.");
      setSelectedShopifyProductGid("");
      return;
    }
    setSelectedShopifyProductGid((current) => {
      if (current && response.products.some((product) => product.productGid === current)) {
        return current;
      }
      return response.products[0]?.productGid || "";
    });
  };

  const handleUseSelectedShopifyProduct = () => {
    if (!selectedShopifyProductGid) {
      toast.error("Select a Shopify product first.");
      return;
    }
    setShopifyProductGidDraft(selectedShopifyProductGid);
  };

  const handleCreateOffer = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!productId) return;
    if (!offerName.trim()) {
      toast.error("Offer name is required.");
      return;
    }
    if (!offerBusinessModel.trim()) {
      toast.error("Business model is required.");
      return;
    }
    await createOffer.mutateAsync({
      productId,
      name: offerName.trim(),
      businessModel: offerBusinessModel.trim(),
      description: offerDescription.trim() || undefined,
    });
    resetOfferForm();
    setIsOfferModalOpen(false);
  };

  const handleAddBonus = async (offerId: string) => {
    const bonusProductId = (bonusSelectionByOffer[offerId] || "").trim();
    if (!bonusProductId) {
      toast.error("Select a bonus product.");
      return;
    }
    await addOfferBonus.mutateAsync({ offerId, bonusProductId });
    setBonusSelectionByOffer((prev) => ({ ...prev, [offerId]: "" }));
  };

  const handleRemoveBonus = async (offerId: string, bonusProductId: string) => {
    await removeOfferBonus.mutateAsync({ offerId, bonusProductId });
  };

  const primaryAssetId = productDetail?.primary_asset_id ?? null;
  const bonusProductCandidates = useMemo(() => {
    if (!productDetail) return [];
    return products
      .filter((item) => item.client_id === productDetail.client_id && item.id !== productDetail.id)
      .map((item) => ({
        id: item.id,
        title: item.title,
        shopifyProductGid: item.shopify_product_gid || null,
      }));
  }, [productDetail, products]);
  const filteredAssets = useMemo(() => {
    if (!productId) return [] as ProductAsset[];
    return productAssets.filter((asset) => asset.product_id === productId);
  }, [productAssets, productId]);
  const offerNameById = useMemo(() => {
    const mapping = new Map<string, string>();
    (productDetail?.offers || []).forEach((offer) => mapping.set(offer.id, offer.name));
    return mapping;
  }, [productDetail?.offers]);
  const orderedAssets = useMemo(() => {
    if (!primaryAssetId) return filteredAssets;
    const primary = filteredAssets.find((asset) => asset.id === primaryAssetId);
    const rest = filteredAssets.filter((asset) => asset.id !== primaryAssetId);
    return primary ? [primary, ...rest] : filteredAssets;
  }, [filteredAssets, primaryAssetId]);
  const shopifyCatalogProducts = listShopifyProducts.data?.products || [];
  const hasShopifyCheckoutVariant = useMemo(
    () =>
      Boolean(
        productDetail?.variants.some(
          (variant) =>
            variant.provider === "shopify" &&
            typeof variant.external_price_id === "string" &&
            variant.external_price_id.startsWith("gid://shopify/ProductVariant/"),
        ),
      ),
    [productDetail?.variants],
  );
  const shopifyState = shopifyStatus?.state || "error";
  const shopifyStatusTone = useMemo(() => {
    if (shopifyState === "ready") return "success" as const;
    if (shopifyState === "not_connected" || shopifyState === "installed_missing_storefront_token") return "neutral" as const;
    return "danger" as const;
  }, [shopifyState]);
  const shopifyStatusLabel = useMemo(() => {
    if (shopifyState === "ready") return "Ready";
    if (shopifyState === "not_connected") return "Not connected";
    if (shopifyState === "installed_missing_storefront_token") return "Missing token";
    if (shopifyState === "multiple_installations_conflict") return "Store conflict";
    return "Error";
  }, [shopifyState]);
  const shopifyStatusMessage = useMemo(() => {
    if (shopifyStatus?.message) return shopifyStatus.message;
    if (shopifyStatusError && typeof shopifyStatusError === "object" && "message" in shopifyStatusError) {
      const message = (shopifyStatusError as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return message;
    }
    if (typeof shopifyStatusError === "string" && shopifyStatusError.trim()) return shopifyStatusError;
    return "Checking Shopify connection status.";
  }, [shopifyStatus?.message, shopifyStatusError]);
  const isShopifyConnectionMutating =
    createShopifyInstallUrl.isPending ||
    updateShopifyInstallation.isPending ||
    disconnectShopifyInstallation.isPending ||
    setDefaultShop.isPending;
  const isShopifyReady = shopifyState === "ready";
  const hasMappedShopifyProduct = Boolean((productDetail?.shopify_product_gid || "").trim());

  if (!workspace) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-surface px-4 py-6 text-sm text-content-muted">
        Select a workspace to view product details.
      </div>
    );
  }

  if (!productId) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-surface px-4 py-6 text-sm text-content-muted">
        Select a product to view details.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={productDetail?.title || "Product detail"}
        description={productDetail?.description || "Review product variants, assets, and pricing."}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => navigate("/workspaces/products")}>
              Back to products
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setIsOfferModalOpen(true)} disabled={!productDetail}>
              New offer
            </Button>
            <Button size="sm" onClick={() => setIsVariantModalOpen(true)} disabled={!productDetail}>
              New variant
            </Button>
          </div>
        }
      />

      {isLoadingDetail ? (
        <div className="rounded-lg border border-border bg-surface px-4 py-6 text-sm text-content-muted">Loading product…</div>
      ) : !productDetail ? (
        <div className="rounded-lg border border-border bg-surface px-4 py-6 text-sm text-content-muted">
          Unable to load product.
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="space-y-6">
            <div className="rounded-md border border-border bg-surface-2 p-4">
              <div className="text-xs font-semibold uppercase text-content-muted">Overview</div>
              <div className="mt-2 text-sm text-content">
                <div className="font-semibold">{productDetail.title}</div>
                <div className="text-xs text-content-muted">
                  {productDetail.product_type || "No product type"}
                </div>
              </div>
              <div className="mt-3 grid gap-3 text-xs text-content-muted sm:grid-cols-2">
                <div>
                  <div className="font-semibold text-content">Benefits</div>
                  {productDetail.primary_benefits?.length ? productDetail.primary_benefits.join(", ") : "—"}
                </div>
                <div>
                  <div className="font-semibold text-content">Disclaimers</div>
                  {productDetail.disclaimers?.length ? productDetail.disclaimers.join(", ") : "—"}
                </div>
              </div>
            </div>

            <div className="rounded-md border border-border bg-surface-2 p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase text-content-muted">Shopify Connection</div>
                  <div className="text-xs text-content-muted">
                    Connect the store and verify setup before mapping products.
                  </div>
                </div>
                <Badge tone={shopifyStatusTone}>{isLoadingShopifyStatus ? "Checking…" : shopifyStatusLabel}</Badge>
              </div>
              <div className="text-xs text-content-muted">
                {shopifyStatusMessage}
              </div>
              {shopifyStatus?.missingScopes?.length ? (
                <div className="text-xs text-danger">Missing scopes: {shopifyStatus.missingScopes.join(", ")}</div>
              ) : null}
              {shopifyStatus?.shopDomains?.length ? (
                <div className="text-xs text-content-muted">Connected stores: {shopifyStatus.shopDomains.join(", ")}</div>
              ) : null}
              {shopifyState === "multiple_installations_conflict" && shopifyStatus?.shopDomains?.length ? (
                <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                  <select
                    className="w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content shadow-sm"
                    value={defaultShopDomainDraft}
                    onChange={(e) => setDefaultShopDomainDraft(e.target.value)}
                    disabled={setDefaultShop.isPending || disconnectShopifyInstallation.isPending}
                  >
                    {shopifyStatus.shopDomains.map((shopDomain) => (
                      <option key={shopDomain} value={shopDomain}>
                        {shopDomain}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void handleSetDefaultShop()}
                    disabled={!defaultShopDomainDraft.trim() || setDefaultShop.isPending || disconnectShopifyInstallation.isPending}
                  >
                    {setDefaultShop.isPending ? "Saving…" : "Set default shop"}
                  </Button>
                </div>
              ) : null}
              <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
                <Input
                  placeholder="example-shop.myshopify.com"
                  value={shopifyShopDomainDraft}
                  onChange={(e) => setShopifyShopDomainDraft(e.target.value)}
                  disabled={isShopifyConnectionMutating}
                />
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void refetchShopifyStatus()}
                  disabled={isLoadingShopifyStatus || isShopifyConnectionMutating}
                >
                  Refresh
                </Button>
                <Button
                  size="sm"
                  onClick={() => void handleConnectShopify()}
                  disabled={
                    !productClientId ||
                    !shopifyShopDomainDraft.trim() ||
                    isShopifyConnectionMutating
                  }
                >
                  {createShopifyInstallUrl.isPending ? "Redirecting…" : "Connect Shopify"}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => void handleDisconnectShopify()}
                  disabled={!productClientId || !shopifyShopDomainDraft.trim() || isShopifyConnectionMutating}
                >
                  {disconnectShopifyInstallation.isPending ? "Disconnecting…" : "Disconnect Shopify"}
                </Button>
              </div>
              <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                <Input
                  type="password"
                  placeholder="Storefront access token"
                  value={storefrontAccessTokenDraft}
                  onChange={(e) => setStorefrontAccessTokenDraft(e.target.value)}
                  disabled={isShopifyConnectionMutating}
                />
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void handleSetStorefrontToken()}
                  disabled={
                    !productClientId ||
                    !shopifyShopDomainDraft.trim() ||
                    !storefrontAccessTokenDraft.trim() ||
                    isShopifyConnectionMutating
                  }
                >
                  {updateShopifyInstallation.isPending ? "Saving…" : "Set storefront token"}
                </Button>
              </div>
            </div>

            <div className="rounded-md border border-border bg-surface-2 p-4 space-y-3">
              <div>
                <div className="text-xs font-semibold uppercase text-content-muted">Shopify Product Mapping</div>
                <div className="text-xs text-content-muted">
                  Required for bonus products and Shopify offer verification.
                </div>
              </div>
              {!isShopifyReady ? (
                <div className="text-xs text-danger">
                  Shopify mapping is blocked until connection state is Ready.
                </div>
              ) : null}
              {isShopifyReady && !hasShopifyCheckoutVariant ? (
                <div className="text-xs text-danger">
                  Checkout readiness is blocked: add at least one variant with provider `shopify` and external price ID
                  `gid://shopify/ProductVariant/...`.
                </div>
              ) : null}
              {isShopifyReady && !hasMappedShopifyProduct ? (
                <div className="rounded-md border border-border bg-surface p-3 space-y-2">
                  <div className="text-xs font-semibold uppercase text-content-muted">Create In Shopify</div>
                  <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_180px]">
                    <Input
                      placeholder="Shopify product title"
                      value={createShopifyTitleDraft}
                      onChange={(e) => setCreateShopifyTitleDraft(e.target.value)}
                      disabled={createShopifyProductForProduct.isPending}
                    />
                    <Input
                      placeholder="Variant title"
                      value={createShopifyVariantTitleDraft}
                      onChange={(e) => setCreateShopifyVariantTitleDraft(e.target.value)}
                      disabled={createShopifyProductForProduct.isPending}
                    />
                  </div>
                  <div className="grid gap-2 md:grid-cols-[180px_120px_auto]">
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="Price"
                      value={createShopifyVariantPriceDraft}
                      onChange={(e) => setCreateShopifyVariantPriceDraft(e.target.value)}
                      disabled={createShopifyProductForProduct.isPending}
                    />
                    <Input
                      placeholder="USD"
                      value={createShopifyCurrencyDraft}
                      onChange={(e) => setCreateShopifyCurrencyDraft(e.target.value)}
                      disabled={createShopifyProductForProduct.isPending}
                    />
                    <Button
                      size="sm"
                      onClick={() => void handleCreateShopifyProduct()}
                      disabled={
                        createShopifyProductForProduct.isPending ||
                        !createShopifyTitleDraft.trim() ||
                        !createShopifyVariantTitleDraft.trim() ||
                        !createShopifyVariantPriceDraft.trim()
                      }
                    >
                      {createShopifyProductForProduct.isPending ? "Creating…" : "Create product in Shopify"}
                    </Button>
                  </div>
                </div>
              ) : null}
              {shopifyImportSummary ? (
                <div className="rounded-md border border-border bg-surface p-3 space-y-1">
                  <div className="text-xs font-semibold uppercase text-content-muted">Latest Shopify Import</div>
                  <div className="text-xs text-content-muted">
                    Store: {shopifyImportSummary.shopDomain} · Product: {shopifyImportSummary.productGid}
                  </div>
                  <div className="text-xs text-content-muted">
                    Imported {shopifyImportSummary.variantCount} variant
                    {shopifyImportSummary.variantCount === 1 ? "" : "s"}
                    {shopifyImportSummary.variantTitles.length
                      ? `: ${shopifyImportSummary.variantTitles.join(", ")}`
                      : "."}
                  </div>
                </div>
              ) : null}
              {isShopifyReady && hasMappedShopifyProduct ? (
                <div className="text-xs text-content-muted">
                  Shopify product is already mapped for this product. Clear mapping if you need to create a new Shopify
                  product.
                </div>
              ) : null}
              <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                <Input
                  placeholder="Search Shopify products by title or handle"
                  value={shopifyProductSearchQuery}
                  onChange={(e) => setShopifyProductSearchQuery(e.target.value)}
                  disabled={!isShopifyReady || listShopifyProducts.isPending}
                />
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void handleSearchShopifyProducts()}
                  disabled={!isShopifyReady || listShopifyProducts.isPending}
                >
                  {listShopifyProducts.isPending ? "Searching…" : "Search Shopify"}
                </Button>
              </div>
              {shopifyCatalogProducts.length ? (
                <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                  <select
                    className="w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content shadow-sm"
                    value={selectedShopifyProductGid}
                    onChange={(e) => setSelectedShopifyProductGid(e.target.value)}
                    disabled={!isShopifyReady}
                  >
                    {shopifyCatalogProducts.map((product) => (
                      <option key={product.productGid} value={product.productGid}>
                        {product.title} ({product.handle}) · {product.status}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleUseSelectedShopifyProduct}
                    disabled={!isShopifyReady || !selectedShopifyProductGid}
                  >
                    Use selected product
                  </Button>
                </div>
              ) : null}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Shopify product GID</label>
                <Input
                  placeholder="gid://shopify/Product/1234567890"
                  value={shopifyProductGidDraft}
                  onChange={(e) => setShopifyProductGidDraft(e.target.value)}
                  disabled={!isShopifyReady || updateProduct.isPending}
                />
              </div>
              <div className="flex justify-end">
                <Button
                  size="sm"
                  onClick={handleSaveShopifyProductGid}
                  disabled={
                    !isShopifyReady ||
                    updateProduct.isPending ||
                    shopifyProductGidDraft === (productDetail.shopify_product_gid || "")
                  }
                >
                  {updateProduct.isPending ? "Saving…" : "Save Shopify mapping"}
                </Button>
              </div>
            </div>

            <div className="rounded-md border border-border bg-surface-2 p-3 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase text-content-muted">Assets</div>
                  <div className="text-xs text-content-muted">Images, PDFs, docs, and videos.</div>
                </div>
                <div className="flex items-center gap-2">
                  {primaryAssetId ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => handleSetPrimary(null)}
                      disabled={updateProduct.isPending}
                    >
                      Clear primary
                    </Button>
                  ) : null}
                  <input
                    ref={assetInputRef}
                    className="hidden"
                    type="file"
                    multiple
                    accept="image/*,video/*,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={handleAssetUpload}
                  />
                  <Button
                    size="sm"
                    onClick={() => assetInputRef.current?.click()}
                    disabled={!productId || uploadProductAssets.isPending}
                  >
                    {uploadProductAssets.isPending ? "Uploading…" : "Upload assets"}
                  </Button>
                </div>
              </div>

              {isLoadingAssets ? (
                <div className="text-xs text-content-muted">Loading assets…</div>
              ) : orderedAssets.length ? (
                <div className="space-y-2">
                  {orderedAssets.map((asset) => {
                    const url = asset.download_url || undefined;
                    const sizeLabel = formatBytes(asset.size_bytes);
                    const isImage = asset.asset_kind === "image";
                    const isVideo = asset.asset_kind === "video";
                    return (
                      <div
                        key={asset.id}
                        className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-2"
                      >
                        <div className="flex items-center gap-3 min-w-[220px]">
                          <div className="h-12 w-12 shrink-0 rounded-md border border-border bg-surface-2 flex items-center justify-center overflow-hidden">
                            {isImage && url ? (
                              <img src={url} alt={asset.alt || assetLabel(asset)} className="h-full w-full object-cover" />
                            ) : isVideo ? (
                              <div className="text-[10px] font-semibold text-content-muted uppercase">Video</div>
                            ) : (
                              <div className="text-[10px] font-semibold text-content-muted uppercase">Doc</div>
                            )}
                          </div>
                          <div className="space-y-1">
                            <div className="text-xs font-semibold text-content">{assetLabel(asset)}</div>
                            <div className="text-[11px] text-content-muted">
                              {asset.content_type || asset.asset_kind}
                              {sizeLabel ? ` · ${sizeLabel}` : ""}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {isImage ? (
                            asset.is_primary ? (
                              <span className="rounded-full border border-border px-2 py-1 text-[10px] font-semibold uppercase text-content-muted">
                                Primary
                              </span>
                            ) : (
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => handleSetPrimary(asset.id)}
                                disabled={updateProduct.isPending}
                              >
                                Set primary
                              </Button>
                            )
                          ) : null}
                          {url ? (
                            <a
                              className="text-xs font-semibold text-primary hover:underline"
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open
                            </a>
                          ) : (
                            <span className="text-xs text-content-muted">No file</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-xs text-content-muted">No assets yet.</div>
              )}
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase text-content-muted">Offers</div>
                  <div className="text-xs text-content-muted">Primary package plus bonus products.</div>
                </div>
                <Button size="sm" variant="secondary" onClick={() => setIsOfferModalOpen(true)}>
                  New offer
                </Button>
              </div>

              <div className="mt-4 space-y-3">
                {productDetail.offers?.length ? (
                  productDetail.offers.map((offer) => {
                    const linkedBonusProductIds = new Set((offer.bonuses || []).map((bonus) => bonus.bonus_product.id));
                    const addableBonuses = bonusProductCandidates.filter((candidate) => !linkedBonusProductIds.has(candidate.id));
                    const selectedBonusProductId = bonusSelectionByOffer[offer.id] || "";
                    return (
                      <div key={offer.id} className="rounded-md border border-border bg-surface-2 p-3 space-y-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-content truncate">{offer.name}</div>
                            <div className="text-xs text-content-muted">{offer.business_model}</div>
                            {offer.description ? <div className="text-xs text-content-muted mt-1">{offer.description}</div> : null}
                          </div>
                          <div className="text-[10px] text-content-muted">{offer.id.slice(0, 8)}</div>
                        </div>

                        <div className="space-y-2">
                          <div className="text-xs font-semibold text-content">Bonuses</div>
                          {offer.bonuses?.length ? (
                            <div className="space-y-2">
                              {offer.bonuses.map((bonus) => (
                                <div
                                  key={bonus.id}
                                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-surface px-3 py-2"
                                >
                                  <div className="min-w-0">
                                    <div className="text-xs font-semibold text-content">{bonus.bonus_product.title}</div>
                                    <div className="text-[11px] text-content-muted">
                                      {bonus.bonus_product.shopify_product_gid || "Missing Shopify product GID"}
                                    </div>
                                  </div>
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={() => handleRemoveBonus(offer.id, bonus.bonus_product.id)}
                                    disabled={removeOfferBonus.isPending}
                                  >
                                    Remove
                                  </Button>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-xs text-content-muted">No bonuses attached.</div>
                          )}
                        </div>

                        <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                          <select
                            className="w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content shadow-sm"
                            value={selectedBonusProductId}
                            onChange={(e) =>
                              setBonusSelectionByOffer((prev) => ({
                                ...prev,
                                [offer.id]: e.target.value,
                              }))
                            }
                          >
                            <option value="">Select bonus product</option>
                            {addableBonuses.map((candidate) => (
                              <option key={candidate.id} value={candidate.id} disabled={!candidate.shopifyProductGid}>
                                {candidate.title}
                                {candidate.shopifyProductGid ? "" : " (missing Shopify GID)"}
                              </option>
                            ))}
                          </select>
                          <Button
                            size="sm"
                            onClick={() => handleAddBonus(offer.id)}
                            disabled={!selectedBonusProductId || addOfferBonus.isPending}
                          >
                            {addOfferBonus.isPending ? "Adding…" : "Add bonus"}
                          </Button>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="text-sm text-content-muted">No offers yet.</div>
                )}
              </div>
            </div>

            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase text-content-muted">Variants</div>
                  <div className="text-xs text-content-muted">Pricing, provider, and option values.</div>
                </div>
                <Button size="sm" variant="secondary" onClick={() => setIsVariantModalOpen(true)}>
                  New variant
                </Button>
              </div>

              <div className="mt-4 space-y-3">
                {productDetail.variants.length ? (
                  productDetail.variants.map((variant) => (
                    <div key={variant.id} className="rounded-md border border-border bg-surface-2 p-3 space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-content truncate">{variant.title}</div>
                          <div className="text-xs text-content-muted">
                            {variant.price} {variant.currency.toUpperCase()}
                            {variant.provider ? ` · ${variant.provider}` : ""}
                          </div>
                        </div>
                        <div className="text-[10px] text-content-muted">{variant.id.slice(0, 8)}</div>
                      </div>
                      <div className="grid gap-2 text-xs text-content-muted">
                        <div>
                          <span className="font-semibold text-content">Shopify mapping:</span>{" "}
                          {variant.provider === "shopify" &&
                          typeof variant.external_price_id === "string" &&
                          variant.external_price_id.startsWith("gid://shopify/ProductVariant/")
                            ? "Ready"
                            : variant.provider === "shopify"
                              ? "Missing valid Shopify variant GID"
                              : "Not Shopify"}
                        </div>
                        <div>
                          <span className="font-semibold text-content">External price ID:</span>{" "}
                          {variant.external_price_id || "—"}
                        </div>
                        <div>
                          <span className="font-semibold text-content">Offer:</span>{" "}
                          {variant.offer_id ? offerNameById.get(variant.offer_id) || variant.offer_id : "—"}
                        </div>
                        <div>
                          <span className="font-semibold text-content">Option values:</span>{" "}
                          {variant.option_values ? JSON.stringify(variant.option_values) : "—"}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-content-muted">No variants yet.</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <DialogRoot open={isOfferModalOpen} onOpenChange={setIsOfferModalOpen}>
        <DialogContent>
          <DialogTitle>New offer</DialogTitle>
          <DialogDescription>Create an offer package and attach bonus products after creation.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreateOffer}>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Offer name</label>
              <Input
                placeholder="e.g. Buy 1 Get Bonus Stack"
                value={offerName}
                onChange={(e) => setOfferName(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Business model</label>
              <Input
                placeholder="one_time"
                value={offerBusinessModel}
                onChange={(e) => setOfferBusinessModel(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Description (optional)</label>
              <Input
                placeholder="Optional offer description"
                value={offerDescription}
                onChange={(e) => setOfferDescription(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={!productId || createOffer.isPending}>
                {createOffer.isPending ? "Creating…" : "Create offer"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>

      <DialogRoot open={isVariantModalOpen} onOpenChange={setIsVariantModalOpen}>
        <DialogContent>
          <DialogTitle>New variant</DialogTitle>
          <DialogDescription>Attach pricing and (optionally) a Stripe or Shopify external ID.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreateVariant}>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Title</label>
              <Input
                placeholder="e.g. Default"
                value={variantTitle}
                onChange={(e) => setVariantTitle(e.target.value)}
                required
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Price (cents)</label>
                <Input
                  placeholder="4900"
                  value={variantPrice}
                  onChange={(e) => setVariantPrice(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Currency</label>
                <Input
                  placeholder="usd"
                  value={variantCurrency}
                  onChange={(e) => setVariantCurrency(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Offer (optional)</label>
              <select
                className="w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content shadow-sm"
                value={variantOfferId}
                onChange={(e) => setVariantOfferId(e.target.value)}
                disabled={!productDetail?.offers?.length}
              >
                <option value="">
                  {productDetail?.offers?.length ? "No linked offer" : "No offers available"}
                </option>
                {(productDetail?.offers || []).map((offer) => (
                  <option key={offer.id} value={offer.id}>
                    {offer.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Provider</label>
                <Input
                  placeholder="stripe | shopify"
                  value={variantProvider}
                  onChange={(e) => setVariantProvider(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">External price ID</label>
                <Input
                  placeholder="price_... or gid://shopify/ProductVariant/..."
                  value={variantExternalId}
                  onChange={(e) => setVariantExternalId(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Option values (JSON)</label>
              <textarea
                className="min-h-[120px] w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-content"
                placeholder='{"size":"M","add_on":"none"}'
                value={variantOptionValues}
                onChange={(e) => setVariantOptionValues(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={!productId || createVariant.isPending}>
                {createVariant.isPending ? "Creating…" : "Create variant"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
