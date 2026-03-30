/**
 * Medusa B2C Product Page
 *
 * Product detail page featuring:
 * - Multi-image gallery
 * - Sticky desktop and mobile purchase actions
 * - Product information tabs
 * - Related products
 */

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useFunnelRuntime } from "@/funnels/puckConfig";
import { listProducts } from "@/lib/medusa";
import type { MedusaProduct, MedusaProductVariant } from "@/types/commerce";
import { useB2CRuntime } from "../B2CRuntimeProvider";
import {
  resolveB2CActionRadius,
  resolveB2CHeadingFont,
  resolveB2CSurfaceRadius,
  useB2CCTATheme,
  useB2CTheme,
} from "../useB2CTheme";
import { B2CStarterShell } from "./B2CStarterShell";
import { resolveB2CSitePath } from "./sitePath";
import {
  StoreProductCard,
  StorefrontNotFoundState,
  formatPrice,
  getProductImageGallery,
} from "./storefrontPrimitives";

export type MedusaB2CProductPageProps = {
  productHandle?: string;
};

type ProductInfoSection = "product_information" | "shipping_returns";

function resolveVariantLabel(variant: MedusaProductVariant): string {
  if (variant.title?.trim() && variant.title.toLowerCase() !== "default variant") {
    return variant.title.trim();
  }

  if (Array.isArray(variant.options)) {
    const optionSummary = variant.options
      .map((option) => {
        const value = option?.value?.trim();
        const title = option?.option?.title?.trim();
        if (!value) return null;
        return title ? `${title}: ${value}` : value;
      })
      .filter((value): value is string => Boolean(value));
    if (optionSummary.length > 0) {
      return optionSummary.join(" / ");
    }
  }

  if (variant.options && typeof variant.options === "object") {
    const optionSummary = Object.entries(variant.options)
      .map(([key, value]) => {
        const normalizedValue = String(value || "").trim();
        if (!normalizedValue) return null;
        return `${key}: ${normalizedValue}`;
      })
      .filter((value): value is string => Boolean(value));
    if (optionSummary.length > 0) {
      return optionSummary.join(" / ");
    }
  }

  return variant.title?.trim() || "Default";
}

function readMetadataString(
  metadata: Record<string, unknown> | null | undefined,
  keys: string[],
): string | null {
  if (!metadata) {
    return null;
  }

  for (const key of keys) {
    const raw = metadata[key];
    if (typeof raw === "string" && raw.trim()) {
      return raw.trim();
    }
    if (typeof raw === "number" && Number.isFinite(raw)) {
      return String(raw);
    }
  }

  return null;
}

function ProductPageSkeleton() {
  const { tokens } = useB2CTheme();
  const skeletonStyle: CSSProperties = {
    backgroundColor: tokens.colorBackgroundAlt || "rgba(17, 24, 39, 0.08)",
    borderRadius: resolveB2CSurfaceRadius(tokens),
  };

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.2fr)_minmax(0,0.95fr)]">
      <div className="animate-pulse space-y-4">
        <div className="h-10 w-2/3" style={skeletonStyle} />
        <div className="h-6 w-1/3" style={skeletonStyle} />
        <div className="h-4 w-full" style={skeletonStyle} />
        <div className="h-4 w-4/5" style={skeletonStyle} />
        <div className="h-56 w-full" style={skeletonStyle} />
      </div>
      <div className="animate-pulse space-y-4">
        <div className="aspect-square w-full" style={skeletonStyle} />
        <div className="aspect-square w-full" style={skeletonStyle} />
      </div>
      <div className="animate-pulse space-y-4">
        <div className="h-64 w-full" style={skeletonStyle} />
        <div className="h-12 w-full" style={skeletonStyle} />
      </div>
    </div>
  );
}

export function MedusaB2CProductPage({ productHandle: propHandle }: MedusaB2CProductPageProps) {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const runtime = useFunnelRuntime();
  const {
    currentProduct,
    cartLoading,
    loadProductByHandle,
    addToCart,
    navigateToCart,
    navigateToHome,
    navigateToStore,
    navigateToProduct,
  } = useB2CRuntime();
  const { tokens, isThemed } = useB2CTheme();
  const ctaTheme = useB2CCTATheme();

  const [product, setProduct] = useState<MedusaProduct | null>(null);
  const [productLoading, setProductLoading] = useState(true);
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [addedToCart, setAddedToCart] = useState(false);
  const [addToCartError, setAddToCartError] = useState<string | null>(null);
  const addedToCartTimerRef = useRef<number | null>(null);
  const [relatedProducts, setRelatedProducts] = useState<MedusaProduct[]>([]);
  const [mobileOptionsOpen, setMobileOptionsOpen] = useState(false);
  const [openSection, setOpenSection] = useState<ProductInfoSection | null>("product_information");

  const pathHandle = resolveB2CSitePath(location.pathname, runtime).handle;
  const resolvedHandle =
    propHandle || pathHandle || searchParams.get("handle") || searchParams.get("product");
  const galleryRefs = useRef<Array<HTMLDivElement | null>>([]);
  const initialRuntimeProduct =
    currentProduct &&
    (!resolvedHandle ||
      !currentProduct.handle ||
      currentProduct.handle === resolvedHandle)
      ? currentProduct
      : null;
  const runtimeProductMatchesResolvedHandle = Boolean(
    initialRuntimeProduct && (!resolvedHandle || initialRuntimeProduct.handle === resolvedHandle),
  );

  useEffect(() => {
    if (initialRuntimeProduct) {
      setProduct((currentValue) => {
        if (
          currentValue?.id === initialRuntimeProduct.id &&
          currentValue?.handle === initialRuntimeProduct.handle
        ) {
          return currentValue;
        }
        return initialRuntimeProduct;
      });
      setProductLoading(false);
    }
  }, [initialRuntimeProduct]);

  useEffect(() => {
    let cancelled = false;

    if (!resolvedHandle) {
      setProduct(null);
      setProductLoading(false);
      return;
    }

    if (runtimeProductMatchesResolvedHandle) {
      return;
    }

    setProductLoading(true);
    setAddedToCart(false);
    setAddToCartError(null);
    setProduct(null);

    const load = async () => {
      const loadedProduct = await loadProductByHandle(resolvedHandle);
      if (cancelled) {
        return;
      }

      setProduct(loadedProduct);
      setProductLoading(false);
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [loadProductByHandle, resolvedHandle, runtimeProductMatchesResolvedHandle]);

  useEffect(() => {
    if (product?.variants?.length) {
      setSelectedVariantId(product.variants[0].id);
    } else {
      setSelectedVariantId(null);
    }
    setQuantity(1);
  }, [product]);

  useEffect(() => {
    let cancelled = false;

    if (!product) {
      setRelatedProducts([]);
      return;
    }

    const loadRelatedProducts = async () => {
      const requests = [];
      if (product.collection_id) {
        requests.push(listProducts({ collectionId: [product.collection_id], limit: 8 }));
      }
      if (product.categories?.[0]?.id) {
        requests.push(listProducts({ categoryId: [product.categories[0].id], limit: 8 }));
      }
      requests.push(listProducts({ limit: 8 }));

      for (const request of requests) {
        try {
          const result = await request;
          const candidates = result.products.filter((candidate) => candidate.id !== product.id);
          if (candidates.length > 0) {
            if (!cancelled) {
              setRelatedProducts(candidates.slice(0, 4));
            }
            return;
          }
        } catch {
          // Keep walking through the fallback chain.
        }
      }

      if (!cancelled) {
        setRelatedProducts([]);
      }
    };

    void loadRelatedProducts();

    return () => {
      cancelled = true;
    };
  }, [product]);

  const variants = product?.variants || [];
  const selectedVariant = variants.find((variant) => variant.id === selectedVariantId) || variants[0];
  const selectedPriceAmount =
    selectedVariant?.calculated_price?.calculated_amount ??
    selectedVariant?.prices?.[0]?.amount;
  const selectedPriceCurrency =
    selectedVariant?.calculated_price?.currency_code ??
    selectedVariant?.prices?.[0]?.currency_code ??
    "usd";
  const imageGallery = product ? getProductImageGallery(product) : [];

  const productInformationRows = useMemo(() => {
    if (!product) {
      return [];
    }

    const material = readMetadataString(product.metadata, [
      "material",
      "materials",
      "fabric",
    ]);
    const countryOfOrigin = readMetadataString(product.metadata, [
      "country_of_origin",
      "origin_country",
      "origin",
    ]);
    const productType =
      readMetadataString(product.metadata, ["type"]) ||
      product.type?.value?.trim() ||
      null;
    const weight =
      readMetadataString(product.metadata, ["weight"]) ||
      (typeof product.weight === "number" ? `${product.weight} g` : null);
    const dimensions =
      readMetadataString(product.metadata, ["dimensions"]) ||
      (product.height || product.width || product.length
        ? `${product.length || "—"} × ${product.width || "—"} × ${product.height || "—"}`
        : null);

    return [
      { label: "Material", value: material },
      { label: "Country of Origin", value: countryOfOrigin },
      { label: "Type", value: productType },
      { label: "Weight", value: weight },
      { label: "Dimensions", value: dimensions },
    ].filter((row): row is { label: string; value: string } => Boolean(row.value));
  }, [product]);

  const pageStyle: CSSProperties = {
    backgroundColor: tokens.colorBackground || "#ffffff",
    color: tokens.colorText || "#111827",
  };
  const titleStyle: CSSProperties = {
    color: tokens.colorText || "#111827",
    fontFamily: resolveB2CHeadingFont(tokens),
  };
  const textStyle: CSSProperties = {
    color: tokens.colorText || "#111827",
  };
  const mutedTextStyle: CSSProperties = {
    color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.64)",
  };
  const surfaceStyle: CSSProperties = {
    backgroundColor: tokens.colorBackgroundAlt || tokens.colorBackground || "#ffffff",
    borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
    borderRadius: resolveB2CSurfaceRadius(tokens),
  };
  const borderStyle: CSSProperties = {
    borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
  };
  const secondaryButtonStyle: CSSProperties = {
    backgroundColor: tokens.colorBackground || "#ffffff",
    borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
    color: tokens.colorText || "#111827",
    borderRadius: resolveB2CActionRadius(tokens),
  };
  const primaryButtonStyle: CSSProperties = {
    backgroundColor: tokens.colorPrimary || "#111827",
    borderColor: tokens.colorPrimary || "#111827",
    color: tokens.colorPrimaryText || "#ffffff",
    borderRadius: ctaTheme.style?.borderRadius || resolveB2CActionRadius(tokens),
  };

  useEffect(() => {
    return () => {
      if (addedToCartTimerRef.current) {
        window.clearTimeout(addedToCartTimerRef.current);
      }
    };
  }, []);

  const handleAddToCart = async () => {
    if (!selectedVariant?.id) {
      setAddToCartError("Choose a product variant before adding to cart.");
      return;
    }

    setAddToCartError(null);

    try {
      await addToCart(selectedVariant.id, quantity);
      setAddedToCart(true);
      setMobileOptionsOpen(false);
      if (addedToCartTimerRef.current) {
        window.clearTimeout(addedToCartTimerRef.current);
      }
      addedToCartTimerRef.current = window.setTimeout(() => setAddedToCart(false), 3000);
    } catch (err) {
      setAddToCartError(
        err instanceof Error ? err.message : "Failed to add this item to cart.",
      );
    }
  };

  if (productLoading) {
    return (
      <B2CStarterShell>
        <main className="px-4 py-8 sm:px-6 lg:px-8" style={pageStyle}>
          <div className="mx-auto max-w-7xl">
            <ProductPageSkeleton />
          </div>
        </main>
      </B2CStarterShell>
    );
  }

  if (!product) {
    return (
      <B2CStarterShell>
        <main style={pageStyle}>
          <StorefrontNotFoundState
            title="Product not found"
            description="The product you're looking for doesn't exist or is no longer available."
            primaryLabel="Continue shopping"
            onPrimary={navigateToStore}
            secondaryLabel="Go home"
            onSecondary={navigateToHome}
          />
        </main>
      </B2CStarterShell>
    );
  }

  return (
    <B2CStarterShell>
      <main className="px-4 py-8 pb-32 sm:px-6 lg:px-8 lg:pb-10" style={pageStyle}>
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-10 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.2fr)_minmax(0,0.95fr)]">
            <section className="space-y-6 lg:sticky lg:top-24 lg:self-start">
              <div className="space-y-4">
                <h1 className="text-3xl font-medium lg:text-4xl" style={titleStyle}>
                  {product.title}
                </h1>
                {typeof selectedPriceAmount === "number" ? (
                  <p className="text-2xl" style={textStyle}>
                    {formatPrice(selectedPriceAmount, selectedPriceCurrency)}
                  </p>
                ) : null}
                {product.description ? (
                  <p className="max-w-xl text-sm leading-7 lg:text-base" style={mutedTextStyle}>
                    {product.description}
                  </p>
                ) : null}
              </div>

              <div className="space-y-3 border-t pt-6" style={borderStyle}>
                {[
                  {
                    id: "product_information" as const,
                    label: "Product Information",
                    content:
                      productInformationRows.length > 0 ? (
                        <dl className="space-y-3">
                          {productInformationRows.map((row) => (
                            <div key={row.label} className="flex items-start justify-between gap-4 text-sm">
                              <dt className="font-medium" style={textStyle}>
                                {row.label}
                              </dt>
                              <dd className="text-right" style={mutedTextStyle}>
                                {row.value}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      ) : (
                        <p className="text-sm" style={mutedTextStyle}>
                          More product details will appear here when Medusa metadata is available.
                        </p>
                      ),
                  },
                  {
                    id: "shipping_returns" as const,
                    label: "Shipping & Returns",
                    content: (
                      <ul className="space-y-3 text-sm" style={mutedTextStyle}>
                        <li>Fast delivery: 3-5 business days.</li>
                        <li>Simple exchanges: 30-day return policy.</li>
                        <li>Easy returns: Free returns on all orders.</li>
                      </ul>
                    ),
                  },
                ].map((section) => (
                  <div key={section.id} className="border-b pb-3" style={borderStyle}>
                    <button
                      type="button"
                      onClick={() =>
                        setOpenSection((current) =>
                          current === section.id ? null : section.id,
                        )
                      }
                      className="flex w-full items-center justify-between gap-4 py-2 text-left"
                    >
                      <span className="text-base font-medium" style={textStyle}>
                        {section.label}
                      </span>
                      <span
                        className={`text-lg transition-transform ${
                          openSection === section.id ? "rotate-45" : ""
                        }`}
                        style={mutedTextStyle}
                      >
                        +
                      </span>
                    </button>
                    {openSection === section.id ? (
                      <div className="pt-2">{section.content}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-4">
              {imageGallery.length > 0 ? (
                <>
                  <div className="flex gap-2 overflow-x-auto pb-2 lg:hidden">
                    {imageGallery.map((image, index) => (
                      <button
                        key={`${image}-${index}`}
                        type="button"
                        onClick={() =>
                          galleryRefs.current[index]?.scrollIntoView({
                            behavior: "smooth",
                            block: "start",
                          })
                        }
                        className="h-16 w-16 flex-shrink-0 overflow-hidden border"
                        style={surfaceStyle}
                      >
                        <img src={image} alt="" className="h-full w-full object-cover" />
                      </button>
                    ))}
                  </div>

                  <div className="space-y-4">
                    {imageGallery.map((image, index) => (
                      <div
                        key={`${image}-${index}`}
                        ref={(node) => {
                          galleryRefs.current[index] = node;
                        }}
                        className="overflow-hidden border"
                        style={surfaceStyle}
                      >
                        <img
                          src={image}
                          alt={`${product.title} image ${index + 1}`}
                          className="aspect-square h-full w-full object-cover"
                          loading={index < 3 ? "eager" : "lazy"}
                        />
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="flex aspect-square items-center justify-center border" style={surfaceStyle}>
                  <p className="text-sm" style={mutedTextStyle}>
                    No product imagery available
                  </p>
                </div>
              )}
            </section>

            <aside className="hidden lg:block lg:sticky lg:top-24 lg:self-start">
              <div className="space-y-6 border-t pt-6" style={borderStyle}>
                {variants.length > 1 ? (
                  <div className="space-y-3">
                    <p className="text-sm font-medium" style={textStyle}>
                      Variant
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {variants.map((variant) => (
                        <button
                          key={variant.id}
                          type="button"
                          onClick={() => setSelectedVariantId(variant.id)}
                          className="flex h-10 items-center justify-center border px-4 text-sm transition-colors"
                          style={
                            selectedVariant?.id === variant.id && isThemed
                              ? {
                                  ...ctaTheme.style,
                                  borderRadius:
                                    ctaTheme.style?.borderRadius || resolveB2CActionRadius(tokens),
                                }
                              : {
                                  ...secondaryButtonStyle,
                                  borderRadius: secondaryButtonStyle.borderRadius,
                                }
                          }
                        >
                          {resolveVariantLabel(variant)}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="space-y-3">
                  <p className="text-sm font-medium" style={textStyle}>
                    Quantity
                  </p>
                  <div className="flex h-10 w-fit items-center border" style={surfaceStyle}>
                    <button
                      type="button"
                      onClick={() => setQuantity((current) => Math.max(1, current - 1))}
                      className="flex h-full w-10 items-center justify-center text-base"
                      style={textStyle}
                    >
                      -
                    </button>
                    <span className="flex min-w-12 items-center justify-center px-4 text-center" style={textStyle}>
                      {quantity}
                    </span>
                    <button
                      type="button"
                      onClick={() => setQuantity((current) => current + 1)}
                      className="flex h-full w-10 items-center justify-center text-base"
                      style={textStyle}
                    >
                      +
                    </button>
                  </div>
                </div>

                <div className="space-y-3">
                  <button
                    type="button"
                    onClick={() => void handleAddToCart()}
                    disabled={cartLoading || !selectedVariant?.id}
                    className="flex h-10 w-full items-center justify-center rounded-full border px-4 text-sm font-medium text-white disabled:opacity-50"
                    style={primaryButtonStyle}
                  >
                    {cartLoading ? "Adding..." : "Add to Cart"}
                  </button>
                  {addedToCart ? (
                    <button
                      type="button"
                      onClick={() => navigateToCart()}
                      className="flex h-10 w-full items-center justify-center rounded-full border px-4 text-sm font-medium"
                      style={secondaryButtonStyle}
                    >
                      View Cart
                    </button>
                  ) : null}
                  {addToCartError ? (
                    <p className="text-sm" style={{ color: "#dc2626" }}>{addToCartError}</p>
                  ) : null}
                </div>
              </div>
            </aside>
          </div>

          {relatedProducts.length > 0 ? (
            <section className="mt-16 space-y-6">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <p className="text-sm uppercase tracking-[0.18em]" style={mutedTextStyle}>
                    You may also like
                  </p>
                  <h2 className="mt-2 text-2xl font-medium" style={titleStyle}>
                    Related products
                  </h2>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
                {relatedProducts.map((relatedProduct) => (
                  <StoreProductCard
                    key={relatedProduct.id}
                    product={relatedProduct}
                    onClick={() => navigateToProduct(relatedProduct.handle)}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <div
          className="fixed inset-x-0 bottom-0 z-40 border-t bg-white px-4 py-3 lg:hidden"
          style={{
            backgroundColor: tokens.colorBackground || "#ffffff",
            borderTopColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
          }}
        >
          <div className="mx-auto flex max-w-7xl items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileOptionsOpen(true)}
              className="min-w-0 flex h-10 flex-1 items-center border px-4 text-left text-sm"
              style={secondaryButtonStyle}
            >
              <span className="block truncate" style={textStyle}>
                {selectedVariant ? resolveVariantLabel(selectedVariant) : "Select variant"}
              </span>
              <span className="ml-auto block text-xs" style={mutedTextStyle}>
                Qty {quantity}
              </span>
            </button>
            <div className="hidden text-right sm:block">
              {typeof selectedPriceAmount === "number" ? (
                <p className="text-sm font-medium" style={textStyle}>
                  {formatPrice(selectedPriceAmount, selectedPriceCurrency)}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => void handleAddToCart()}
              disabled={cartLoading || !selectedVariant?.id}
              className="flex h-10 items-center justify-center rounded-full border px-4 text-sm font-medium text-white disabled:opacity-50"
              style={primaryButtonStyle}
            >
              {cartLoading ? "Adding..." : "Add"}
            </button>
          </div>
        </div>

        {mobileOptionsOpen ? (
          <div className="fixed inset-0 z-50 bg-black/30 lg:hidden" onClick={() => setMobileOptionsOpen(false)}>
            <div
              className="absolute inset-x-0 bottom-0 rounded-t-2xl border px-4 pb-8 pt-5"
              style={{
                backgroundColor: tokens.colorBackground || "#ffffff",
                borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
              }}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="mx-auto mb-5 h-1.5 w-12 rounded-full" style={{ backgroundColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)" }} />
              <div className="space-y-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm uppercase tracking-[0.18em]" style={mutedTextStyle}>
                      Choose your setup
                    </p>
                    <h2 className="mt-2 text-xl font-medium" style={titleStyle}>
                      {product.title}
                    </h2>
                  </div>
                  <button type="button" onClick={() => setMobileOptionsOpen(false)} style={mutedTextStyle}>
                    Close
                  </button>
                </div>

                {variants.length > 1 ? (
                  <div className="space-y-3">
                    <p className="text-sm font-medium" style={textStyle}>
                      Variant
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {variants.map((variant) => (
                        <button
                          key={variant.id}
                          type="button"
                          onClick={() => setSelectedVariantId(variant.id)}
                          className="flex h-10 items-center justify-center border px-4 text-sm"
                          style={
                            selectedVariant?.id === variant.id && isThemed
                              ? {
                                  ...ctaTheme.style,
                                  borderRadius:
                                    ctaTheme.style?.borderRadius || resolveB2CActionRadius(tokens),
                                }
                              : {
                                  ...secondaryButtonStyle,
                                  borderRadius: secondaryButtonStyle.borderRadius,
                                }
                          }
                        >
                          {resolveVariantLabel(variant)}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="space-y-3">
                  <p className="text-sm font-medium" style={textStyle}>
                    Quantity
                  </p>
                  <div className="flex h-10 w-fit items-center border" style={surfaceStyle}>
                    <button
                      type="button"
                      onClick={() => setQuantity((current) => Math.max(1, current - 1))}
                      className="flex h-full w-10 items-center justify-center text-base"
                      style={textStyle}
                    >
                      -
                    </button>
                    <span className="flex min-w-12 items-center justify-center px-4 text-center" style={textStyle}>
                      {quantity}
                    </span>
                    <button
                      type="button"
                      onClick={() => setQuantity((current) => current + 1)}
                      className="flex h-full w-10 items-center justify-center text-base"
                      style={textStyle}
                    >
                      +
                    </button>
                  </div>
                </div>

                <div className="space-y-3">
                  {typeof selectedPriceAmount === "number" ? (
                    <p className="text-lg font-medium" style={textStyle}>
                      {formatPrice(selectedPriceAmount, selectedPriceCurrency)}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void handleAddToCart()}
                    disabled={cartLoading || !selectedVariant?.id}
                    className="flex h-10 w-full items-center justify-center rounded-full border px-4 text-sm font-medium text-white disabled:opacity-50"
                    style={primaryButtonStyle}
                  >
                    {cartLoading ? "Adding..." : "Add to Cart"}
                  </button>
                  {addToCartError ? (
                    <p className="text-sm" style={{ color: "#dc2626" }}>{addToCartError}</p>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </main>
    </B2CStarterShell>
  );
}
