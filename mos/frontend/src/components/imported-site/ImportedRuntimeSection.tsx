import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMaybeB2CRuntime } from "@/components/commerce/b2c";
import { useApiClient } from "@/api/client";
import type { SiteDetail } from "@/api/sites";
import {
  buildImportedRuntimeSrcDoc,
  normalizeImportedHeadAssets,
} from "@/components/imported-site/importedRuntime";
import { useImportedRuntimeContext } from "@/components/imported-site/ImportedTemplateBlocks";
import { resolveRuntimeSitePath, useFunnelRuntime } from "@/funnels/puckConfig";
import { toast } from "@/components/ui/toast";
import type { MedusaProduct, MedusaProductVariant } from "@/types/commerce";
import type { ProductAsset, ProductDetail } from "@/types/products";

type ImportedRuntimeSectionProps = {
  id?: string;
  originalType?: string;
  runtimeSource?: string;
  headAssets?: unknown;
  sectionLabel?: string;
  componentName?: string;
  sectionTargetId?: string;
  textOverrides?: Array<Record<string, unknown>>;
  buttonOverrides?: Array<Record<string, unknown>>;
  imageOverrides?: Array<Record<string, unknown>>;
};

type RuntimeFrameAssets = {
  reactUmdSource: string;
  reactDomUmdSource: string;
};

type ImportedRuntimeCommerceActionPayload = {
  action?: unknown;
  selectedOfferTitle?: unknown;
  selectionStrategy?: unknown;
  replaceCart?: unknown;
};

type ImportedRuntimeNavigationPayload = {
  href?: unknown;
};

type ImportedPurchaseRuntimeData = {
  ctaBaseLabel?: string;
  imageUrls?: string[];
  variants: Array<{
    title: string;
    priceLabel: string;
    compareAtLabel?: string;
    commerceVariantId?: string;
  }>;
};

const compiledSourceCache = new Map<string, Promise<string>>();

function readViewportHeightPx(): number {
  if (typeof window === "undefined") return 900;
  const next = window.visualViewport?.height || window.innerHeight || 900;
  return Math.max(1, Math.round(next));
}

function hashString(value: string): string {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(36);
}

function compileImportedRuntimeSource(runtimeSource: string): Promise<string> {
  const cached = compiledSourceCache.get(runtimeSource);
  if (cached) return cached;

  const next = import("typescript").then((tsModule) => {
    const ts = "default" in tsModule ? tsModule.default : tsModule;
    const output = ts.transpileModule(runtimeSource, {
      compilerOptions: {
        jsx: ts.JsxEmit.React,
        jsxFactory: "React.createElement",
        jsxFragmentFactory: "React.Fragment",
        module: ts.ModuleKind.None,
        target: ts.ScriptTarget.ES2020,
      },
      reportDiagnostics: false,
    }).outputText;

    if (!output.trim()) {
      throw new Error("Imported section runtime compiled to empty output.");
    }

    return output;
  });

  compiledSourceCache.set(runtimeSource, next);
  return next;
}

function ImportedRuntimeError({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div className="rounded-lg border border-danger/30 bg-danger/10 p-4 text-sm text-content">
      <div className="font-semibold text-danger">{title}</div>
      <div className="mt-2 whitespace-pre-wrap text-content">{message}</div>
    </div>
  );
}

function normalizeComparableLabel(value: unknown): string {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function extractDurationComparableKey(value: unknown): string {
  const normalized = normalizeComparableLabel(value);
  const match = normalized.match(/(\d+)\s*day/);
  return match ? `${match[1]}-day` : "";
}

function isExternalNavigationHref(href: string): boolean {
  return /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//");
}

function formatCurrencyLabel(amountCents: number | null | undefined, currencyCode: string | null | undefined): string {
  if (typeof amountCents !== "number" || !Number.isFinite(amountCents)) {
    return "";
  }
  const normalizedCurrencyCode = (currencyCode || "USD").trim().toUpperCase() || "USD";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: normalizedCurrencyCode,
    maximumFractionDigits: 0,
  }).format(amountCents / 100);
}

function resolveVariantAmounts(variant: MedusaProductVariant): {
  amountCents: number | null;
  compareAtAmountCents: number | null;
  currencyCode: string | null;
} {
  const calculatedAmount = variant.calculated_price?.calculated_amount;
  const originalAmount = variant.calculated_price?.original_amount;
  const calculatedCurrencyCode = variant.calculated_price?.currency_code;
  const fallbackPrice = Array.isArray(variant.prices) ? variant.prices[0] : null;
  const amountCents =
    typeof calculatedAmount === "number"
      ? calculatedAmount
      : typeof fallbackPrice?.amount === "number"
        ? fallbackPrice.amount
        : null;
  const compareAtAmountCents =
    typeof originalAmount === "number" && typeof amountCents === "number" && originalAmount > amountCents
      ? originalAmount
      : null;
  const currencyCode =
    typeof calculatedCurrencyCode === "string" && calculatedCurrencyCode.trim()
      ? calculatedCurrencyCode
      : typeof fallbackPrice?.currency_code === "string" && fallbackPrice.currency_code.trim()
        ? fallbackPrice.currency_code
        : null;
  return {
    amountCents,
    compareAtAmountCents,
    currencyCode,
  };
}

function buildImportedPurchaseRuntimeData(
  product: MedusaProduct,
  actionLabel: string | null,
): ImportedPurchaseRuntimeData | null {
  const variants = Array.isArray(product.variants) ? product.variants : [];
  const runtimeVariants = variants
    .map((variant) => {
      const title = String(variant.title || "").trim();
      const { amountCents, compareAtAmountCents, currencyCode } = resolveVariantAmounts(variant);
      const priceLabel = formatCurrencyLabel(amountCents, currencyCode);
      if (!title || !priceLabel) {
        return null;
      }
      const compareAtLabel = formatCurrencyLabel(compareAtAmountCents, currencyCode);
      return {
        title,
        priceLabel,
        compareAtLabel: compareAtLabel || undefined,
        commerceVariantId: String(variant.id || "").trim() || undefined,
      };
    })
    .filter((variant): variant is ImportedPurchaseRuntimeData["variants"][number] => Boolean(variant));

  if (!runtimeVariants.length) {
    return null;
  }

  return {
    ctaBaseLabel: actionLabel?.trim() || undefined,
    imageUrls: [
      ...new Set(
        [
          ...(Array.isArray(product.images) ? product.images.map((image) => String(image?.url || "").trim()) : []),
          String(product.thumbnail || "").trim(),
        ].filter(Boolean),
      ),
    ],
    variants: runtimeVariants,
  };
}

function mergeImportedPurchaseRuntimeData(
  primary: ImportedPurchaseRuntimeData | null,
  secondary: ImportedPurchaseRuntimeData | null,
): ImportedPurchaseRuntimeData | null {
  if (!primary && !secondary) return null;
  if (!primary) return secondary;
  if (!secondary) return primary;

  const primaryByTitle = new Map<string, ImportedPurchaseRuntimeData["variants"][number]>();
  for (const variant of primary.variants) {
    const normalizedTitle = normalizeComparableLabel(variant.title);
    const durationKey = extractDurationComparableKey(variant.title);
    if (normalizedTitle && !primaryByTitle.has(normalizedTitle)) {
      primaryByTitle.set(normalizedTitle, variant);
    }
    if (durationKey && !primaryByTitle.has(durationKey)) {
      primaryByTitle.set(durationKey, variant);
    }
  }
  const secondaryKeys = new Set<string>();
  const mergedVariants: ImportedPurchaseRuntimeData["variants"] = secondary.variants.map((secondaryVariant) => {
    const secondaryTitleKey = normalizeComparableLabel(secondaryVariant.title);
    const secondaryDurationKey = extractDurationComparableKey(secondaryVariant.title);
    if (secondaryTitleKey) {
      secondaryKeys.add(secondaryTitleKey);
    }
    if (secondaryDurationKey) {
      secondaryKeys.add(secondaryDurationKey);
    }
    const primaryVariant =
      primaryByTitle.get(secondaryTitleKey) ||
      primaryByTitle.get(secondaryDurationKey);
    return {
      title: secondaryVariant.title || primaryVariant?.title || "",
      priceLabel: primaryVariant?.priceLabel || secondaryVariant.priceLabel || "",
      compareAtLabel: secondaryVariant.compareAtLabel || primaryVariant?.compareAtLabel || undefined,
      commerceVariantId: primaryVariant?.commerceVariantId || secondaryVariant.commerceVariantId || undefined,
    };
  });
  for (const primaryVariant of primary.variants) {
    const primaryTitleKey = normalizeComparableLabel(primaryVariant.title);
    const primaryDurationKey = extractDurationComparableKey(primaryVariant.title);
    if (
      (primaryTitleKey && secondaryKeys.has(primaryTitleKey)) ||
      (primaryDurationKey && secondaryKeys.has(primaryDurationKey))
    ) {
      continue;
    }
    mergedVariants.push(primaryVariant);
  }

  return {
    ctaBaseLabel: primary.ctaBaseLabel || secondary.ctaBaseLabel || undefined,
    imageUrls: [
      ...new Set(
        [
          ...(Array.isArray(primary.imageUrls) ? primary.imageUrls : []),
          ...(Array.isArray(secondary.imageUrls) ? secondary.imageUrls : []),
        ].filter(Boolean),
      ),
    ],
    variants: mergedVariants.filter((variant) => variant.title && variant.priceLabel),
  };
}

function collectProductAssetImageUrls(product: ProductDetail): string[] {
  const nextUrls = new Set<string>();

  const pushIfPresent = (value: unknown) => {
    if (typeof value !== "string") return;
    const normalized = value.trim();
    if (normalized) nextUrls.add(normalized);
  };

  pushIfPresent(product.primary_asset_url);
  for (const asset of Array.isArray(product.assets) ? product.assets : []) {
    pushIfPresent(asset.download_url);
    if (asset && asset.content && typeof asset.content === "object") {
      const record = asset.content as ProductAsset["content"];
      pushIfPresent(record.url);
      pushIfPresent(record.src);
      pushIfPresent(record.download_url);
      pushIfPresent(record.downloadUrl);
    }
  }

  return Array.from(nextUrls);
}

function buildImportedPurchaseRuntimeDataFromSiteProduct(
  product: ProductDetail,
  actionLabel: string | null,
): ImportedPurchaseRuntimeData | null {
  const runtimeVariants = (Array.isArray(product.variants) ? product.variants : [])
    .map((variant) => {
      const title = String(variant.title || "").trim();
      const currencyCode = String(variant.currency || "USD").trim().toUpperCase() || "USD";
      const priceLabel = formatCurrencyLabel(variant.price, currencyCode);
      if (!title || !priceLabel) {
        return null;
      }
      const compareAtLabel = formatCurrencyLabel(variant.compare_at_price, currencyCode);
      return {
        title,
        priceLabel,
        compareAtLabel: compareAtLabel || undefined,
        commerceVariantId: String(variant.external_price_id || "").trim() || undefined,
      };
    })
    .filter((variant): variant is ImportedPurchaseRuntimeData["variants"][number] => Boolean(variant));

  if (!runtimeVariants.length) {
    return null;
  }

  return {
    ctaBaseLabel: actionLabel?.trim() || undefined,
    imageUrls: collectProductAssetImageUrls(product),
    variants: runtimeVariants,
  };
}

export function ImportedRuntimeSection({
  id,
  originalType,
  runtimeSource,
  headAssets,
  sectionLabel,
  componentName,
  sectionTargetId,
  textOverrides,
  buttonOverrides,
  imageOverrides,
}: ImportedRuntimeSectionProps) {
  const sharedRuntime = useImportedRuntimeContext();
  const funnelRuntime = useFunnelRuntime();
  const b2cRuntime = useMaybeB2CRuntime();
  const { get: apiGet } = useApiClient();
  const loadProductByHandle = b2cRuntime?.loadProductByHandle;
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const commerceActionPendingRef = useRef(false);
  const initialOverridesFrameRevisionRef = useRef<string | null>(null);
  const initialTextOverridesRef = useRef<Array<Record<string, unknown>>>([]);
  const initialButtonOverridesRef = useRef<Array<Record<string, unknown>>>([]);
  const initialImageOverridesRef = useRef<Array<Record<string, unknown>>>([]);
  const frameId = useMemo(() => `imported-runtime-${id || Math.random().toString(36).slice(2)}`, [id]);
  const [compiledSource, setCompiledSource] = useState<string | null>(null);
  const [frameAssets, setFrameAssets] = useState<RuntimeFrameAssets | null>(null);
  const [height, setHeight] = useState(96);
  const [error, setError] = useState<string | null>(null);
  const [viewportHeightPx, setViewportHeightPx] = useState<number>(readViewportHeightPx);
  const [purchaseRuntimeData, setPurchaseRuntimeData] = useState<ImportedPurchaseRuntimeData | null>(null);
  const resolvedRuntimeSource = runtimeSource || sharedRuntime.runtimeSource;
  const textOverridesJson = JSON.stringify(textOverrides || []);
  const buttonOverridesJson = JSON.stringify(buttonOverrides || []);
  const imageOverridesJson = JSON.stringify(imageOverrides || []);
  const medusaActionLabel = useMemo(() => {
    const actionOverride = Array.isArray(buttonOverrides)
      ? buttonOverrides.find((entry) => String(entry?.action || "").trim() === "medusa_buy_now")
      : null;
    return typeof actionOverride?.text === "string" ? actionOverride.text.trim() : "";
  }, [buttonOverrides]);
  const normalizedHeadAssets = useMemo(
    () => normalizeImportedHeadAssets(headAssets ?? sharedRuntime.headAssets),
    [headAssets, sharedRuntime.headAssets],
  );
  const runtimeRevision = useMemo(
    () =>
      hashString(
        JSON.stringify({
          frameId,
          compiledSource,
          frameAssets,
          normalizedHeadAssets,
          sectionLabel,
          viewportHeightPx,
          componentName,
          sectionTargetId,
          purchaseRuntimeData,
        }),
      ),
    [
      compiledSource,
      componentName,
      frameAssets,
      frameId,
      normalizedHeadAssets,
      purchaseRuntimeData,
      sectionLabel,
      sectionTargetId,
      viewportHeightPx,
    ],
  );

  if (initialOverridesFrameRevisionRef.current !== runtimeRevision) {
    initialOverridesFrameRevisionRef.current = runtimeRevision;
    initialTextOverridesRef.current = textOverridesJson
      ? (JSON.parse(textOverridesJson) as Array<Record<string, unknown>>)
      : [];
    initialButtonOverridesRef.current = buttonOverridesJson
      ? (JSON.parse(buttonOverridesJson) as Array<Record<string, unknown>>)
      : [];
    initialImageOverridesRef.current = imageOverridesJson
      ? (JSON.parse(imageOverridesJson) as Array<Record<string, unknown>>)
      : [];
  }

  const srcDoc = useMemo(() => {
    if (!compiledSource || !frameAssets) return null;
    return buildImportedRuntimeSrcDoc({
      frameId,
      sectionLabel,
      headAssets: normalizedHeadAssets,
      compiledSource,
      reactUmdSource: frameAssets.reactUmdSource,
      reactDomUmdSource: frameAssets.reactDomUmdSource,
      viewportHeightPx,
      componentName,
      sectionTargetId,
      initialTextOverrides: initialTextOverridesRef.current,
      initialButtonOverrides: initialButtonOverridesRef.current,
      initialImageOverrides: initialImageOverridesRef.current,
      purchaseRuntimeData,
    });
  }, [
    compiledSource,
    frameAssets,
    frameId,
    normalizedHeadAssets,
    purchaseRuntimeData,
    sectionLabel,
    viewportHeightPx,
    componentName,
    sectionTargetId,
  ]);
  const frameRevision = useMemo(() => (srcDoc ? `${frameId}-${hashString(srcDoc)}` : frameId), [frameId, srcDoc]);
  const overridesRevision = useMemo(
    () => hashString(`${textOverridesJson}|${buttonOverridesJson}|${imageOverridesJson}`),
    [textOverridesJson, buttonOverridesJson, imageOverridesJson],
  );

  const handleCommerceAction = useCallback(
    async (payload: ImportedRuntimeCommerceActionPayload) => {
      if ((payload.action || "") !== "medusa_buy_now") {
        return;
      }
      if (commerceActionPendingRef.current) {
        return;
      }

      if (!b2cRuntime) {
        toast.error("The Medusa storefront runtime is not available for this imported section.");
        return;
      }
      if (!purchaseRuntimeData?.variants?.length) {
        toast.error("This imported purchase section is missing its Medusa product mapping.");
        return;
      }

      const selectedOfferTitle = String(payload.selectedOfferTitle || "").trim();
      if (!selectedOfferTitle) {
        const selectionStrategy = String(payload.selectionStrategy || "").trim();
        toast.error(
          selectionStrategy
            ? `Unable to resolve the selected offer for strategy "${selectionStrategy}".`
            : "Unable to resolve the selected offer for this imported purchase section.",
        );
        return;
      }

      commerceActionPendingRef.current = true;
      try {
        const normalizedSelectedOfferTitle = normalizeComparableLabel(selectedOfferTitle);
        const selectedDurationKey = extractDurationComparableKey(selectedOfferTitle);
        const selectedVariant =
          purchaseRuntimeData.variants.find((variant) => {
            const normalizedVariantTitle = normalizeComparableLabel(variant.title);
            const variantDurationKey = extractDurationComparableKey(variant.title);
            return (
              normalizedVariantTitle === normalizedSelectedOfferTitle ||
              (variantDurationKey && selectedDurationKey && variantDurationKey === selectedDurationKey)
            );
          }) || null;

        if (!selectedVariant) {
          throw new Error(
            `No Medusa variant title matches the imported offer "${selectedOfferTitle}".`,
          );
        }
        if (!selectedVariant.commerceVariantId) {
          throw new Error(`The imported offer "${selectedOfferTitle}" is missing its Medusa variant binding.`);
        }

        if (payload.replaceCart) {
          await b2cRuntime.replaceCartWithVariant(selectedVariant.commerceVariantId, 1);
        } else {
          await b2cRuntime.addToCart(selectedVariant.commerceVariantId, 1);
        }
        await b2cRuntime.refreshCart();
        commerceActionPendingRef.current = false;
        b2cRuntime.navigateToCheckout();
      } catch (reason) {
        toast.error(reason instanceof Error ? reason.message : "Failed to start Medusa checkout from the imported section.");
      } finally {
        commerceActionPendingRef.current = false;
      }
    },
    [b2cRuntime, purchaseRuntimeData],
  );

  const handleNavigationAction = useCallback(
    (payload: ImportedRuntimeNavigationPayload) => {
      const href = String(payload.href || "").trim();
      if (!href) {
        return;
      }

      if (href.startsWith("#")) {
        const targetId = href.slice(1).trim();
        if (!targetId) {
          return;
        }
        const target =
          document.getElementById(targetId) ||
          Array.from(document.querySelectorAll("[data-imported-section-id]")).find(
            (candidate) => candidate.getAttribute("data-imported-section-id") === targetId,
        );
        if (!(target instanceof HTMLElement)) {
          if (funnelRuntime) {
            const homeHref = resolveRuntimeSitePath(funnelRuntime, "");
            window.location.assign(`${homeHref}#${encodeURIComponent(targetId)}`);
            return;
          }
          toast.error(`Imported section target "${targetId}" was not found in this page.`);
          return;
        }
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        if (typeof window.history?.replaceState === "function") {
          window.history.replaceState(window.history.state, "", `#${encodeURIComponent(targetId)}`);
        }
        return;
      }

      const resolvedHref = isExternalNavigationHref(href)
        ? href
        : funnelRuntime
          ? resolveRuntimeSitePath(funnelRuntime, href)
          : href;
      window.location.assign(resolvedHref);
    },
    [funnelRuntime],
  );

  useEffect(() => {
    if (componentName !== "ProductPurchaseSection") {
      setPurchaseRuntimeData(null);
      return;
    }

    let cancelled = false;

    const loadPurchaseRuntimeData = async () => {
      if (b2cRuntime?.siteId && b2cRuntime.siteClientId) {
        const site = await apiGet<Pick<SiteDetail, "productId">>(
          `/sites/${encodeURIComponent(b2cRuntime.siteId)}?clientId=${encodeURIComponent(b2cRuntime.siteClientId)}`,
        );
        const productId = String(site.productId || "").trim();
        if (!productId) {
          throw new Error(`Site "${b2cRuntime.siteId}" is missing a bound product.`);
        }
        const product = await apiGet<ProductDetail>(`/products/${encodeURIComponent(productId)}`);
        if (cancelled) {
          return;
        }
        const localPurchaseRuntimeData = buildImportedPurchaseRuntimeDataFromSiteProduct(product, medusaActionLabel);
        let medusaPurchaseRuntimeData: ImportedPurchaseRuntimeData | null = null;
        const productHandle = String(product.handle || "").trim();
        if (loadProductByHandle && productHandle && productHandle !== "preview-product") {
          const medusaProduct = await loadProductByHandle(productHandle);
          if (cancelled) {
            return;
          }
          medusaPurchaseRuntimeData = medusaProduct
            ? buildImportedPurchaseRuntimeData(medusaProduct, medusaActionLabel)
            : null;
        }
        const nextPurchaseRuntimeData = mergeImportedPurchaseRuntimeData(
          medusaPurchaseRuntimeData,
          localPurchaseRuntimeData,
        );
        setPurchaseRuntimeData((current) => {
          if (JSON.stringify(current) === JSON.stringify(nextPurchaseRuntimeData)) {
            return current;
          }
          return nextPurchaseRuntimeData;
        });
        return;
      }

      const productHandle = (funnelRuntime?.productSlug || "").trim();
      if (!loadProductByHandle || !productHandle || productHandle === "preview-product") {
        throw new Error("Imported purchase runtime requires a bound site product or a real storefront product handle.");
      }

      const product = await loadProductByHandle(productHandle);
      if (cancelled || !product) {
        return;
      }
      const nextPurchaseRuntimeData = buildImportedPurchaseRuntimeData(product, medusaActionLabel);
      setPurchaseRuntimeData((current) => {
        if (JSON.stringify(current) === JSON.stringify(nextPurchaseRuntimeData)) {
          return current;
        }
        return nextPurchaseRuntimeData;
      });
    };

    void loadPurchaseRuntimeData().catch(() => {
      if (!cancelled) {
        setPurchaseRuntimeData(null);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [apiGet, b2cRuntime?.siteClientId, b2cRuntime?.siteId, componentName, funnelRuntime?.productSlug, loadProductByHandle, medusaActionLabel]);

  useEffect(() => {
    let cancelled = false;

    setCompiledSource(null);
    setHeight(96);
    setError(null);

    if (!resolvedRuntimeSource?.trim()) {
      setError("Imported section runtime is missing.");
      return () => {
        cancelled = true;
      };
    }

    compileImportedRuntimeSource(resolvedRuntimeSource)
      .then((output) => {
        if (!cancelled) setCompiledSource(output);
      })
      .catch((reason) => {
        if (cancelled) return;
        const message = reason instanceof Error ? reason.message : "Failed to compile imported section runtime.";
        setError(message);
      });

    return () => {
      cancelled = true;
    };
  }, [resolvedRuntimeSource]);

  useEffect(() => {
    let cancelled = false;

    import("./importedRuntimeFrameAssets")
      .then((module) => {
        if (!cancelled) setFrameAssets(module.importedRuntimeFrameAssets);
      })
      .catch((reason) => {
        if (cancelled) return;
        const message = reason instanceof Error ? reason.message : "Failed to load imported section runtime assets.";
        setError(message);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleResize = () => setViewportHeightPx(readViewportHeightPx());

    window.addEventListener("resize", handleResize);
    window.visualViewport?.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      window.visualViewport?.removeEventListener("resize", handleResize);
    };
  }, []);

  useEffect(() => {
    const ownerWindow = frameRef.current?.ownerDocument?.defaultView || window;
    const handleMessage = (event: MessageEvent) => {
      const payload = event.data;
      if (!payload || typeof payload !== "object") return;
      if ((payload as { source?: unknown }).source !== "mos-imported-runtime") return;
      if ((payload as { frameId?: unknown }).frameId !== frameId) return;

      if ((payload as { type?: unknown }).type === "height") {
        const nextHeight = (payload as { height?: unknown }).height;
        if (typeof nextHeight === "number" && Number.isFinite(nextHeight)) {
          setHeight(Math.max(64, Math.ceil(nextHeight)));
        }
      }

      if ((payload as { type?: unknown }).type === "error") {
        const message = (payload as { message?: unknown }).message;
        setError(typeof message === "string" && message.trim() ? message : "Imported section runtime failed.");
        return;
      }

      if ((payload as { type?: unknown }).type === "commerce-action") {
        void handleCommerceAction(payload as ImportedRuntimeCommerceActionPayload);
        return;
      }

      if ((payload as { type?: unknown }).type === "navigate") {
        handleNavigationAction(payload as ImportedRuntimeNavigationPayload);
      }
    };

    ownerWindow.addEventListener("message", handleMessage);
    return () => ownerWindow.removeEventListener("message", handleMessage);
  }, [frameId, handleCommerceAction, handleNavigationAction, srcDoc]);

  useEffect(() => {
    if (!srcDoc) return;
    const frame = frameRef.current;
    if (!frame) return;

    const requestHeight = () => {
      frame.contentWindow?.postMessage(
        { source: "mos-imported-runtime-host", frameId, type: "request-height" },
        "*",
      );
    };

    requestHeight();
    const timeoutId = window.setTimeout(requestHeight, 100);
    return () => window.clearTimeout(timeoutId);
  }, [frameId, srcDoc]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || !srcDoc) return;

    const payload = {
      source: "mos-imported-runtime-host",
      frameId,
      type: "update-overrides",
      revision: overridesRevision,
      textOverrides: textOverridesJson ? (JSON.parse(textOverridesJson) as Array<Record<string, unknown>>) : [],
      buttonOverrides: buttonOverridesJson ? (JSON.parse(buttonOverridesJson) as Array<Record<string, unknown>>) : [],
      imageOverrides: imageOverridesJson ? (JSON.parse(imageOverridesJson) as Array<Record<string, unknown>>) : [],
    };

    frame.contentWindow?.postMessage(payload, "*");
  }, [frameId, srcDoc, overridesRevision, textOverridesJson, buttonOverridesJson, imageOverridesJson]);

  const resolvedTitle = sectionLabel?.trim() || originalType?.trim() || "Imported section";

  if (error) {
    return <ImportedRuntimeError title={`${resolvedTitle} unavailable`} message={error} />;
  }

  if (!resolvedRuntimeSource?.trim()) {
    return <ImportedRuntimeError title={`${resolvedTitle} unavailable`} message="Imported section runtime is missing." />;
  }

  if (!srcDoc) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4 text-sm text-content-muted">
        Preparing {resolvedTitle.toLowerCase()}...
      </div>
    );
  }

  return (
    <iframe
      key={frameRevision}
      ref={frameRef}
      title={resolvedTitle}
      srcDoc={srcDoc}
      sandbox="allow-forms allow-popups allow-scripts"
      className="block w-full overflow-hidden border-0 bg-transparent"
      style={{ height: `${height}px` }}
      onLoad={() => {
        frameRef.current?.contentWindow?.postMessage(
          { source: "mos-imported-runtime-host", frameId, type: "request-height" },
          "*",
        );
        frameRef.current?.contentWindow?.postMessage(
          {
            source: "mos-imported-runtime-host",
            frameId,
            type: "update-overrides",
            revision: overridesRevision,
            textOverrides: textOverridesJson ? (JSON.parse(textOverridesJson) as Array<Record<string, unknown>>) : [],
            buttonOverrides: buttonOverridesJson ? (JSON.parse(buttonOverridesJson) as Array<Record<string, unknown>>) : [],
            imageOverrides: imageOverridesJson ? (JSON.parse(imageOverridesJson) as Array<Record<string, unknown>>) : [],
          },
          "*",
        );
      }}
    />
  );
}
