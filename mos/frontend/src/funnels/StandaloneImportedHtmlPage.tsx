import { useEffect } from "react";
import { resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";
import type { PublicCommerceVariant } from "@/types/commerce";
import type {
  ImportedHtmlInstrumentationManifest,
  ImportedHtmlTrackEventType,
  PublicFunnelPage,
  PublicFunnelStage,
} from "@/types/funnels";

const apiBaseUrl = resolvePublicApiBaseUrl();

declare global {
  interface Window {
    __mosImportedHtmlStandalonePageId?: string;
  }
}

type StandaloneImportedHtmlPageProps = {
  page: PublicFunnelPage;
  productSlug: string;
  funnelSlug: string;
  visitorId: string;
  sessionId: string;
  htmlDocument: string;
  instrumentationManifest: ImportedHtmlInstrumentationManifest;
  variants: PublicCommerceVariant[];
  pagePathById: Record<string, string>;
  pageStageById: Record<string, PublicFunnelStage>;
};

type SerializedVariant = {
  id: string;
  provider: string | null;
  price: number | null;
  currency: string | null;
  optionValues: Record<string, string> | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeVariantOptionValues(
  optionValues: Record<string, unknown> | null | undefined,
): Record<string, string> | null {
  if (!isRecord(optionValues)) return null;
  const normalizedEntries = Object.entries(optionValues)
    .map(([key, value]) => {
      if (typeof key !== "string") return null;
      const normalizedKey = key.trim();
      if (!normalizedKey || typeof value !== "string") return null;
      const normalizedValue = value.trim();
      if (!normalizedValue) return null;
      return [normalizedKey, normalizedValue] as const;
    })
    .filter((entry): entry is readonly [string, string] => Boolean(entry));
  if (!normalizedEntries.length) return null;
  return Object.fromEntries(normalizedEntries);
}

function serializeVariants(variants: PublicCommerceVariant[]): SerializedVariant[] {
  return variants.map((variant) => ({
    id: variant.id,
    provider: typeof variant.provider === "string" ? variant.provider.trim().toLowerCase() || null : null,
    price: typeof variant.price === "number" ? variant.price : null,
    currency: typeof variant.currency === "string" ? variant.currency.trim() || null : null,
    optionValues: normalizeVariantOptionValues(variant.option_values ?? null),
  }));
}

function buildStandaloneImportedHtmlRuntimeScript({
  page,
  productSlug,
  funnelSlug,
  visitorId,
  sessionId,
  instrumentationManifest,
  variants,
  pagePathById,
  pageStageById,
}: Omit<StandaloneImportedHtmlPageProps, "htmlDocument">): string {
  const scriptConfig = {
    apiBaseUrl,
    pageId: page.pageId,
    pageSlug: page.slug,
    pageStage: page.stage,
    publicationId: page.publicationId,
    productSlug,
    funnelSlug,
    visitorId,
    sessionId,
    tracking: page.tracking ?? null,
    manifest: instrumentationManifest,
    variants: serializeVariants(variants),
    pagePathById,
    pageStageById,
  };

  return `
<script>
(() => {
  const config = ${JSON.stringify(scriptConfig)};

  const META_PIXEL_SCRIPT_ID = "mos-meta-pixel-script";
  const META_PIXEL_SCRIPT_SRC = "https://connect.facebook.net/en_US/fbevents.js";

  const cleanText = (value) => {
    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    return trimmed || null;
  };

  const normalizeText = (value) =>
    String(value || "")
      .replace(/\\s+/g, " ")
      .trim();

  const isRecord = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);

  const getUtmParams = () => {
    const params = new URLSearchParams(window.location.search);
    const utm = {};
    for (const [key, value] of params.entries()) {
      if (key.startsWith("utm_")) {
        utm[key] = value;
      }
    }
    return utm;
  };

  const pendingMetaPurchaseStorageKey = (resolvedSessionId, resolvedFunnelSlug) => {
    const cleanSessionId = cleanText(resolvedSessionId);
    const cleanFunnelSlug = cleanText(resolvedFunnelSlug);
    if (!cleanSessionId || !cleanFunnelSlug) {
      return null;
    }
    return "mos-meta-purchase:" + cleanSessionId + ":" + cleanFunnelSlug;
  };

  const writePendingMetaPurchase = (key, purchase) => {
    if (!key) return;
    sessionStorage.setItem(
      key,
      JSON.stringify({
        ...purchase,
        createdAt: Date.now(),
      }),
    );
  };

  const ensureMetaPixelBootstrap = () => {
    if (!config.tracking || config.tracking.provider !== "meta" || !config.tracking.metaPixelId) {
      return null;
    }
    const pixelId = String(config.tracking.metaPixelId || "").trim();
    if (!pixelId) return null;

    if (!window.fbq) {
      const fbq = function (...args) {
        if (typeof fbq.callMethod === "function") {
          fbq.callMethod(...args);
          return;
        }
        fbq.queue = fbq.queue || [];
        fbq.queue.push(args);
      };
      fbq.queue = [];
      fbq.loaded = true;
      fbq.version = "2.0";
      window.fbq = fbq;
      window._fbq = fbq;
    }

    if (!document.getElementById(META_PIXEL_SCRIPT_ID)) {
      const script = document.createElement("script");
      script.id = META_PIXEL_SCRIPT_ID;
      script.async = true;
      script.src = META_PIXEL_SCRIPT_SRC;
      document.head.appendChild(script);
    }

    if (!Array.isArray(window.__mosMetaPixelIds)) {
      window.__mosMetaPixelIds = [];
    }
    if (!window.__mosMetaPixelIds.includes(pixelId)) {
      window.fbq("init", pixelId);
      window.__mosMetaPixelIds.push(pixelId);
    }
    return pixelId;
  };

  const trackMetaPixelForEvent = (eventType, props) => {
    const pixelId = ensureMetaPixelBootstrap();
    if (!pixelId || typeof window.fbq !== "function") {
      return;
    }
    if (eventType === "sales_to_checkout_click") {
      const variantId = cleanText(props && props.variantId);
      if (variantId) {
        window.fbq("track", "AddToCart", {
          content_ids: [variantId],
          content_type: "product",
          num_items: 1,
        });
      }
      return;
    }
    if (eventType === "pre_sales_to_sales_click") {
      window.fbq("trackCustom", "PreSalesToSalesClick", {
        from_stage: "pre_sales",
        to_stage: "sales",
      });
      return;
    }
    if (eventType === "custom_page_click") {
      window.fbq("trackCustom", "custom_page_click", props || {});
    }
  };

  const trackEvent = async (eventType, props) => {
    trackMetaPixelForEvent(eventType, props || {});
    try {
      await fetch(config.apiBaseUrl + "/public/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          events: [
            {
              eventType,
              publicationId: config.publicationId,
              pageId: config.pageId,
              visitorId: config.visitorId,
              sessionId: config.sessionId,
              path: window.location.pathname + window.location.search,
              referrer: document.referrer || undefined,
              utm: getUtmParams(),
              props: {
                fromPageId: config.pageId,
                slug: config.pageSlug,
                pageStage: config.pageStage,
                ...(props || {}),
              },
            },
          ],
        }),
        keepalive: true,
      });
    } catch (error) {
      console.error("[StandaloneImportedHtmlPage] Tracking failed.", error);
    }
  };

  const normalizeSelection = (selection) => {
    if (!isRecord(selection)) return null;
    const entries = Object.entries(selection)
      .map(([key, value]) => {
        const normalizedKey = cleanText(key);
        const normalizedValue = cleanText(typeof value === "string" ? value : null);
        if (!normalizedKey || !normalizedValue) return null;
        return [normalizedKey, normalizedValue];
      })
      .filter(Boolean);
    if (!entries.length) return null;
    return Object.fromEntries(entries);
  };

  const selectionsMatch = (left, right) => {
    const normalizedLeft = normalizeSelection(left);
    const normalizedRight = normalizeSelection(right);
    if (!normalizedLeft || !normalizedRight) return false;
    const leftEntries = Object.entries(normalizedLeft);
    const rightEntries = Object.entries(normalizedRight);
    if (leftEntries.length !== rightEntries.length) return false;
    return leftEntries.every(([key, value]) => normalizedRight[key] === value);
  };

  const resolveExternalCheckoutUrlForVariant = (items, variantId) => {
    if (!Array.isArray(items) || !variantId) return null;
    const match = items.find((item) => item && item.variantId === variantId && typeof item.url === "string");
    return match ? cleanText(match.url) : null;
  };

  const resolveVariantForCheckout = (checkout, selectionFromDom) => {
    const resolver = checkout && checkout.variantResolver;
    if (!resolver || typeof resolver.type !== "string") {
      throw new Error("Checkout binding is missing a variantResolver.");
    }
    if (resolver.type === "fixed") {
      const variantId = cleanText(resolver.variantId);
      const variant = config.variants.find((candidate) => candidate.id === variantId) || null;
      return {
        variantId,
        variant,
        selection: selectionFromDom || (variant && variant.optionValues ? variant.optionValues : null),
      };
    }
    if (resolver.type === "option_values") {
      return {
        variantId: null,
        variant: config.variants.find((candidate) => selectionsMatch(candidate.optionValues, selectionFromDom)) || null,
        selection: selectionFromDom,
      };
    }
    throw new Error("Unsupported checkout resolver type.");
  };

  const readNodeValue = (node, source) => {
    if (!node) return "";
    if (source === "text") {
      return normalizeText(node.textContent || "");
    }
    if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) {
      return normalizeText(node.value || "");
    }
    return normalizeText(node.textContent || "");
  };

  const readSelectionFromResolver = (resolver, bindingId) => {
    if (!resolver || resolver.type !== "option_values") return null;
    const selection = {};
    const optionSelectors = Array.isArray(resolver.optionSelectors) ? resolver.optionSelectors : [];
    for (const option of optionSelectors) {
      const selector = cleanText(option && option.selector);
      const optionName = cleanText(option && option.name);
      const source = option && option.source === "text" ? "text" : "value";
      if (!selector || !optionName) {
        throw new Error("Checkout binding '" + bindingId + "' has an invalid option selector.");
      }
      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length !== 1) {
        throw new Error(
          "Checkout binding '" +
            bindingId +
            "' option selector '" +
            selector +
            "' matched " +
            String(matches.length) +
            " elements.",
        );
      }
      const value = readNodeValue(matches[0], source);
      if (!value) {
        throw new Error(
          "Checkout binding '" + bindingId + "' could not resolve a non-empty option value for '" + optionName + "'.",
        );
      }
      selection[optionName] = value;
    }
    return selection;
  };

  const bindManifest = () => {
    if (!config.manifest || !Array.isArray(config.manifest.bindings)) return;

    for (const binding of config.manifest.bindings) {
      if (!binding || typeof binding !== "object") continue;
      const selector = cleanText(binding.selector);
      if (!selector) continue;

      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length < 1) {
        console.error(
          "[StandaloneImportedHtmlPage] Binding '" +
            String(binding.id || "unknown") +
            "' selector '" +
            selector +
            "' matched no elements.",
        );
        continue;
      }

      for (const element of matches) {
        if (!(element instanceof HTMLElement)) {
          continue;
        }
        if (element.dataset.mosStandaloneImportedHtmlBound === "true") {
          continue;
        }
        element.dataset.mosStandaloneImportedHtmlBound = "true";
        element.addEventListener("click", async (event) => {
          event.preventDefault();
          event.stopPropagation();

          const buttonText = normalizeText(element.textContent || "");
          try {
            if (binding.type === "internal_navigation") {
              const targetPath = config.pagePathById[String(binding.targetPageId || "")];
              const targetStage = cleanText(config.pageStageById && config.pageStageById[String(binding.targetPageId || "")]);
              if (!targetPath) {
                throw new Error("Target page path is missing for binding '" + String(binding.id || "unknown") + "'.");
              }
              await trackEvent(binding.trackEventType || "custom_page_click", {
                fromStage: config.pageStage,
                toStage: targetStage || "custom",
                targetPageId: binding.targetPageId,
                buttonText: buttonText || undefined,
              });
              window.location.href = targetPath;
              return;
            }

            if (binding.type === "track_only") {
              await trackEvent(binding.trackEventType || "custom_page_click", {
                fromStage: config.pageStage,
                pageId: config.pageId,
                buttonText: buttonText || undefined,
                bindingId: binding.id,
              });
              return;
            }

            if (binding.type !== "checkout" || !binding.checkout) {
              throw new Error("Unsupported binding type.");
            }

            const selectionFromDom = readSelectionFromResolver(binding.checkout.variantResolver, binding.id || "unknown");
            const { variantId, variant, selection } = resolveVariantForCheckout(binding.checkout, selectionFromDom);
            const resolvedVariantId = cleanText(variant && variant.id ? variant.id : variantId);
            const resolvedSelection = normalizeSelection(selection) || {};

            await trackEvent(
              binding.trackEventType || "sales_to_checkout_click",
              {
                fromStage: config.pageStage,
                toStage: "checkout",
                bindingId: binding.id,
                buttonText: buttonText || undefined,
                ...(resolvedVariantId ? { variantId: resolvedVariantId } : {}),
              },
            );

            if (binding.checkout.mode === "external_checkout_url") {
              const checkoutUrl = resolveExternalCheckoutUrlForVariant(
                binding.checkout.externalUrlsByVariant || [],
                resolvedVariantId,
              );
              if (!checkoutUrl) {
                throw new Error("Missing external checkout URL for binding '" + String(binding.id || "unknown") + "'.");
              }
              window.location.href = checkoutUrl;
              return;
            }

            const checkoutReturnUrl = new URL(window.location.href);
            const checkoutCancelUrl = new URL(window.location.href);
            checkoutReturnUrl.searchParams.set("checkout", "success");
            checkoutCancelUrl.searchParams.set("checkout", "cancel");

            const response = await fetch(config.apiBaseUrl + "/public/checkout", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                funnelSlug: config.funnelSlug,
                variantId: resolvedVariantId || undefined,
                selection: resolvedSelection,
                quantity: 1,
                successUrl: checkoutReturnUrl.toString(),
                cancelUrl: checkoutCancelUrl.toString(),
                pageId: config.pageId,
                visitorId: config.visitorId,
                sessionId: config.sessionId,
                utm: getUtmParams(),
              }),
            });

            if (!response.ok) {
              throw new Error((await response.text()) || response.statusText || "Checkout failed.");
            }

            const data = await response.json();
            if (!data || !cleanText(data.checkoutUrl)) {
              throw new Error("Checkout URL is missing.");
            }

            if (variant && variant.provider === "stripe") {
              const pendingKey = pendingMetaPurchaseStorageKey(config.sessionId, config.funnelSlug);
              if (pendingKey) {
                writePendingMetaPurchase(pendingKey, {
                  funnelSlug: config.funnelSlug,
                  pageId: config.pageId,
                  variantId: variant.id,
                  value: typeof variant.price === "number" ? variant.price : null,
                  currency: variant.currency || null,
                  quantity: 1,
                  provider: variant.provider,
                });
              }
            }

            window.location.href = data.checkoutUrl;
          } catch (error) {
            console.error(
              "[StandaloneImportedHtmlPage] Binding '" + String(binding.id || "unknown") + "' failed.",
              error,
            );
          }
        });
      }
    }
  };

  const bindManifestSafely = () => {
    try {
      bindManifest();
    } catch (error) {
      console.error("[StandaloneImportedHtmlPage] Failed to bind manifest.", error);
    }
  };

  bindManifestSafely();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindManifestSafely, { once: true });
  }
  window.addEventListener("load", bindManifestSafely, { once: true });
  window.setTimeout(bindManifestSafely, 0);
  window.setTimeout(bindManifestSafely, 250);
  window.setTimeout(bindManifestSafely, 1000);
})();
</script>`;
}

function injectStandaloneRuntimeScript(
  htmlDocument: string,
  runtimeScript: string,
): string {
  if (/<\/body>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/body>/i, `${runtimeScript}</body>`);
  }
  if (/<\/html>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/html>/i, `${runtimeScript}</html>`);
  }
  return `${htmlDocument}${runtimeScript}`;
}

export function StandaloneImportedHtmlPage(props: StandaloneImportedHtmlPageProps) {
  useEffect(() => {
    const normalizedHtml = props.htmlDocument.trim();
    if (!normalizedHtml) {
      throw new Error("Standalone imported HTML page is empty.");
    }
    if (window.__mosImportedHtmlStandalonePageId === props.page.pageId) {
      return;
    }
    window.__mosImportedHtmlStandalonePageId = props.page.pageId;
    const runtimeScript = buildStandaloneImportedHtmlRuntimeScript(props);
    const nextDocument = injectStandaloneRuntimeScript(normalizedHtml, runtimeScript);
    document.open();
    document.write(nextDocument);
    document.close();
  }, [props]);

  return null;
}
