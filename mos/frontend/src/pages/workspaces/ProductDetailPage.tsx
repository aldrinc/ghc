import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle, DialogClose } from "@/components/ui/dialog";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import {
  useCreateOffer,
  useCreatePricePoint,
  useProduct,
  useProductAssets,
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

function parseList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProductDetailPage() {
  const { productId } = useParams();
  const { workspace } = useWorkspace();
  const { selectProduct } = useProductContext();
  const navigate = useNavigate();

  const { data: productDetail, isLoading: isLoadingDetail } = useProduct(productId);
  const { data: productAssets = [], isLoading: isLoadingAssets } = useProductAssets(productId);
  const updateProduct = useUpdateProduct(productId || "");
  const uploadProductAssets = useUploadProductAssets(productId || "");
  const assetInputRef = useRef<HTMLInputElement | null>(null);

  const createOffer = useCreateOffer();
  const createPricePoint = useCreatePricePoint();
  const [isOfferModalOpen, setIsOfferModalOpen] = useState(false);
  const [isPricePointModalOpen, setIsPricePointModalOpen] = useState(false);
  const [selectedOfferId, setSelectedOfferId] = useState<string | null>(null);

  const [offerName, setOfferName] = useState("");
  const [offerDescription, setOfferDescription] = useState("");
  const [offerBusinessModel, setOfferBusinessModel] = useState("one-time");
  const [offerDifferentiationBullets, setOfferDifferentiationBullets] = useState("");
  const [offerGuaranteeText, setOfferGuaranteeText] = useState("");
  const [offerOptionsSchema, setOfferOptionsSchema] = useState("");

  const [pricePointLabel, setPricePointLabel] = useState("");
  const [pricePointAmount, setPricePointAmount] = useState("");
  const [pricePointCurrency, setPricePointCurrency] = useState("usd");
  const [pricePointProvider, setPricePointProvider] = useState("stripe");
  const [pricePointExternalId, setPricePointExternalId] = useState("");
  const [pricePointOptionValues, setPricePointOptionValues] = useState("");

  useEffect(() => {
    if (!productDetail) return;
    selectProduct(productDetail.id, {
      name: productDetail.name,
      client_id: productDetail.client_id,
      category: productDetail.category ?? null,
    });
  }, [productDetail, selectProduct]);

  const resetOfferForm = () => {
    setOfferName("");
    setOfferDescription("");
    setOfferBusinessModel("one-time");
    setOfferDifferentiationBullets("");
    setOfferGuaranteeText("");
    setOfferOptionsSchema("");
  };

  const resetPricePointForm = () => {
    setPricePointLabel("");
    setPricePointAmount("");
    setPricePointCurrency("usd");
    setPricePointProvider("stripe");
    setPricePointExternalId("");
    setPricePointOptionValues("");
  };

  const handleCreateOffer = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!workspace || !productId) return;
    if (!offerName.trim() || !offerBusinessModel.trim()) {
      toast.error("Offer name and business model are required.");
      return;
    }
    let optionsSchema: Record<string, unknown> | undefined;
    if (offerOptionsSchema.trim()) {
      try {
        const parsed = JSON.parse(offerOptionsSchema);
        if (!parsed || typeof parsed !== "object") {
          throw new Error("Options schema must be a JSON object.");
        }
        optionsSchema = parsed as Record<string, unknown>;
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Invalid options schema JSON.");
        return;
      }
    }
    const payload = {
      productId,
      name: offerName.trim(),
      description: offerDescription.trim() || undefined,
      businessModel: offerBusinessModel.trim(),
      differentiationBullets: offerDifferentiationBullets.trim() ? parseList(offerDifferentiationBullets) : undefined,
      guaranteeText: offerGuaranteeText.trim() || undefined,
      optionsSchema,
    };
    await createOffer.mutateAsync(payload);
    resetOfferForm();
    setIsOfferModalOpen(false);
  };

  const handleCreatePricePoint = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!productId || !selectedOfferId) return;
    const amount = Number(pricePointAmount);
    if (!pricePointLabel.trim() || Number.isNaN(amount) || amount <= 0) {
      toast.error("Price point label and amount are required.");
      return;
    }
    if (!pricePointCurrency.trim()) {
      toast.error("Currency is required.");
      return;
    }
    if (pricePointExternalId.trim() && !pricePointProvider.trim()) {
      toast.error("Provider is required when external price ID is set.");
      return;
    }
    let optionValues: Record<string, unknown> | undefined;
    if (pricePointOptionValues.trim()) {
      try {
        const parsed = JSON.parse(pricePointOptionValues);
        if (!parsed || typeof parsed !== "object") {
          throw new Error("Option values must be a JSON object.");
        }
        optionValues = parsed as Record<string, unknown>;
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Invalid option values JSON.");
        return;
      }
    }
    const payload = {
      productId,
      offerId: selectedOfferId,
      label: pricePointLabel.trim(),
      amountCents: amount,
      currency: pricePointCurrency.trim(),
      provider: pricePointProvider.trim() || undefined,
      externalPriceId: pricePointExternalId.trim() || undefined,
      optionValues,
    };
    await createPricePoint.mutateAsync(payload);
    resetPricePointForm();
    setIsPricePointModalOpen(false);
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

  const primaryAssetId = productDetail?.primary_asset_id ?? null;
  const filteredAssets = useMemo(() => {
    if (!productId) return [] as ProductAsset[];
    return productAssets.filter((asset) => asset.product_id === productId);
  }, [productAssets, productId]);
  const orderedAssets = useMemo(() => {
    if (!primaryAssetId) return filteredAssets;
    const primary = filteredAssets.find((asset) => asset.id === primaryAssetId);
    const rest = filteredAssets.filter((asset) => asset.id !== primaryAssetId);
    return primary ? [primary, ...rest] : filteredAssets;
  }, [filteredAssets, primaryAssetId]);

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
        title={productDetail?.name || "Product detail"}
        description={productDetail?.description || "Review product offers, assets, and pricing."}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => navigate("/workspaces/products")}
            >
              Back to products
            </Button>
            <Button size="sm" onClick={() => setIsOfferModalOpen(true)} disabled={!productDetail}>
              New offer
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
                <div className="font-semibold">{productDetail.name}</div>
                <div className="text-xs text-content-muted">{productDetail.category || "No category"}</div>
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

          <div className="rounded-lg border border-border bg-surface p-4">
            <div className="space-y-3">
              {productDetail.offers.length ? (
                productDetail.offers.map((offer) => (
                  <div key={offer.id} className="rounded-md border border-border bg-surface-2 p-3 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold text-content">{offer.name}</div>
                        <div className="text-xs text-content-muted">{offer.business_model}</div>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          setSelectedOfferId(offer.id);
                          setIsPricePointModalOpen(true);
                        }}
                      >
                        New price point
                      </Button>
                    </div>
                    <div className="text-xs text-content-muted">
                      {offer.options_schema ? "Options schema set" : "No options schema"}
                    </div>
                    <div className="space-y-2">
                      {offer.pricePoints?.length ? (
                        offer.pricePoints.map((pricePoint) => (
                          <div
                            key={pricePoint.id}
                            className="flex items-center justify-between rounded-md border border-border bg-surface px-3 py-2 text-xs"
                          >
                            <div className="font-semibold text-content">{pricePoint.label}</div>
                            <div className="text-content-muted">
                              {pricePoint.amount_cents} {pricePoint.currency.toUpperCase()}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="text-xs text-content-muted">No price points yet.</div>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-content-muted">No offers yet.</div>
              )}
            </div>
          </div>
        </div>
      )}

      <DialogRoot open={isOfferModalOpen} onOpenChange={setIsOfferModalOpen}>
        <DialogContent>
          <DialogTitle>New offer</DialogTitle>
          <DialogDescription>Define an offer for the selected product.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreateOffer}>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Name</label>
              <Input placeholder="Offer name" value={offerName} onChange={(e) => setOfferName(e.target.value)} required />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Description</label>
              <Input
                placeholder="Optional description"
                value={offerDescription}
                onChange={(e) => setOfferDescription(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Business model</label>
              <Input
                placeholder="one-time, subscription"
                value={offerBusinessModel}
                onChange={(e) => setOfferBusinessModel(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Differentiation bullets</label>
              <Input
                placeholder="Comma-separated list"
                value={offerDifferentiationBullets}
                onChange={(e) => setOfferDifferentiationBullets(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Guarantee text</label>
              <Input
                placeholder="Optional guarantee statement"
                value={offerGuaranteeText}
                onChange={(e) => setOfferGuaranteeText(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Options schema (JSON)</label>
              <textarea
                className="min-h-[120px] w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-content"
                placeholder='{"size":{"label":"Size","options":["S","M","L"]}}'
                value={offerOptionsSchema}
                onChange={(e) => setOfferOptionsSchema(e.target.value)}
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

      <DialogRoot open={isPricePointModalOpen} onOpenChange={setIsPricePointModalOpen}>
        <DialogContent>
          <DialogTitle>New price point</DialogTitle>
          <DialogDescription>Attach a Stripe price ID and option values.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreatePricePoint}>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Label</label>
              <Input
                placeholder="e.g. Medium / No add-on"
                value={pricePointLabel}
                onChange={(e) => setPricePointLabel(e.target.value)}
                required
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Amount (cents)</label>
                <Input
                  placeholder="4900"
                  value={pricePointAmount}
                  onChange={(e) => setPricePointAmount(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Currency</label>
                <Input
                  placeholder="usd"
                  value={pricePointCurrency}
                  onChange={(e) => setPricePointCurrency(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Provider</label>
                <Input
                  placeholder="stripe"
                  value={pricePointProvider}
                  onChange={(e) => setPricePointProvider(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Stripe price ID</label>
                <Input
                  placeholder="price_..."
                  value={pricePointExternalId}
                  onChange={(e) => setPricePointExternalId(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Option values (JSON)</label>
              <textarea
                className="min-h-[120px] w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-content"
                placeholder='{"size":"M","add_on":"none"}'
                value={pricePointOptionValues}
                onChange={(e) => setPricePointOptionValues(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={!selectedOfferId || createPricePoint.isPending}>
                {createPricePoint.isPending ? "Creating…" : "Create price point"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
