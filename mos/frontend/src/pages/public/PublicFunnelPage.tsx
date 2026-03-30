import { Render } from "@measured/puck";
import type { Data } from "@measured/puck";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { PublicFunnelMeta, PublicFunnelPage as PublicFunnelPageType } from "@/types/funnels";
import type { PublicFunnelCommerce, SiteCommerceData } from "@/types/commerce";
import { createFunnelPuckConfig, FunnelRuntimeProvider } from "@/funnels/puckConfig";
import { normalizePuckData } from "@/funnels/puckData";
import { buildPublicFunnelPath, isStandaloneBundleMode, parseSitePath, resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";
import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";
import { CommerceRuntimeProvider } from "@/components/commerce/CommerceBlocks";
import { B2CRuntimeProvider } from "@/components/commerce/b2c";
import { setMedusaRuntimeConfig } from "@/lib/medusa";
import {
  buildPurchaseEventParams,
  clearCheckoutQueryParam,
  clearPendingMetaPurchase,
  pendingMetaPurchaseStorageKey,
  readPendingMetaPurchase,
} from "@/lib/metaCheckout";
import { pageViewEventForStage, type RuntimeTrackingEvent } from "@/lib/funnelTracking";
import { mapRuntimeEventToMetaPixelEvents } from "@/lib/metaFunnelEvents";
import { ensureMetaPixel, trackMetaPixelEvent } from "@/lib/metaPixel";

const apiBaseUrl = resolvePublicApiBaseUrl();
const runtimeConfig = createFunnelPuckConfig();
const managedFaviconAttr = "data-mos-managed-favicon";
const managedMetaAttr = "data-mos-managed-meta";

// Site page stages that use the commerce runtime
const SITE_PAGE_STAGES = new Set(["home", "category", "product_detail", "cart", "checkout"]);

type ResolvedPageMetadata = {
  title: string;
  description: string;
  lang: string;
  brandName: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function getBrandName(tokens: unknown): string | null {
  if (!isRecord(tokens)) return null;
  const brand = tokens.brand;
  if (!isRecord(brand)) return null;
  const name = brand.name;
  if (typeof name !== "string") return null;
  const trimmed = name.trim();
  return trimmed || null;
}

function clearManagedFavicons() {
  document
    .querySelectorAll(`link[${managedFaviconAttr}="true"]`)
    .forEach((node) => node.parentNode?.removeChild(node));
}

function clearManagedMetaTags() {
  document
    .querySelectorAll(`meta[${managedMetaAttr}="true"]`)
    .forEach((node) => node.parentNode?.removeChild(node));
}

function appendManagedFavicon(rel: string, href: string, type?: string) {
  const link = document.createElement("link");
  link.setAttribute("rel", rel);
  link.setAttribute("href", href);
  if (type) {
    link.setAttribute("type", type);
  }
  link.setAttribute(managedFaviconAttr, "true");
  document.head.appendChild(link);
}

function hashBrandName(value: string) {
  let hash = 0;
  for (let idx = 0; idx < value.length; idx += 1) {
    hash = (hash * 31 + value.charCodeAt(idx)) >>> 0;
  }
  return hash;
}

function buildBrandInitialFaviconHref(brandName: string) {
  const cleanBrandName = brandName.trim();
  const match = cleanBrandName.match(/[A-Za-z0-9]/);
  if (!match) return null;
  const initial = match[0].toUpperCase();
  const hue = hashBrandName(cleanBrandName) % 360;
  const fill = `hsl(${hue} 62% 42%)`;
  const svg = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">`,
    `<rect width="64" height="64" rx="18" fill="${fill}"/>`,
    `<text x="50%" y="54%" text-anchor="middle" dominant-baseline="middle" fill="#ffffff"`,
    ` font-family="Arial, sans-serif" font-size="32" font-weight="700">${initial}</text>`,
    `</svg>`,
  ].join("");
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function setPageFavicon(brandName: string | null) {
  clearManagedFavicons();
  if (!brandName) return;
  const faviconHref = buildBrandInitialFaviconHref(brandName);
  if (!faviconHref) return;
  appendManagedFavicon("icon", faviconHref, "image/svg+xml");
  appendManagedFavicon("shortcut icon", faviconHref, "image/svg+xml");
  appendManagedFavicon("apple-touch-icon", faviconHref, "image/svg+xml");
}

function ensureNoIndex() {
  const name = "robots";
  const content = "noindex,nofollow";
  const existing = document.querySelector(`meta[name="${name}"]`);
  if (existing) {
    existing.setAttribute("content", content);
    return;
  }
  const meta = document.createElement("meta");
  meta.setAttribute("name", name);
  meta.setAttribute("content", content);
  document.head.appendChild(meta);
}

function syncManagedMeta({
  name,
  property,
  content,
}: {
  name?: string;
  property?: string;
  content?: string;
}) {
  const selector = name ? `meta[name="${name}"]` : property ? `meta[property="${property}"]` : null;
  if (!selector) return;

  const existing = document.querySelector(selector);
  const trimmedContent = typeof content === "string" ? content.trim() : "";
  if (!trimmedContent) {
    if (existing && existing.getAttribute(managedMetaAttr) === "true") {
      existing.parentNode?.removeChild(existing);
    }
    return;
  }

  if (existing) {
    existing.setAttribute("content", trimmedContent);
    existing.setAttribute(managedMetaAttr, "true");
    return;
  }

  const meta = document.createElement("meta");
  if (name) {
    meta.setAttribute("name", name);
  }
  if (property) {
    meta.setAttribute("property", property);
  }
  meta.setAttribute("content", trimmedContent);
  meta.setAttribute(managedMetaAttr, "true");
  document.head.appendChild(meta);
}

function setPageMetadata(metadata: ResolvedPageMetadata | null) {
  if (!metadata) return;
  if (metadata.title.trim()) {
    document.title = metadata.title.trim();
  }
  if (metadata.lang.trim()) {
    document.documentElement.setAttribute("lang", metadata.lang.trim());
  }
  syncManagedMeta({ name: "description", content: metadata.description });
  syncManagedMeta({ property: "og:title", content: metadata.title });
  syncManagedMeta({ property: "og:description", content: metadata.description });
  syncManagedMeta({ property: "og:type", content: "website" });
  syncManagedMeta({ property: "og:url", content: window.location.href });
  syncManagedMeta({ property: "og:site_name", content: metadata.brandName || metadata.title });
  syncManagedMeta({ name: "twitter:card", content: "summary" });
  syncManagedMeta({ name: "twitter:title", content: metadata.title });
  syncManagedMeta({ name: "twitter:description", content: metadata.description });
}

function resolvePageMetadata(page: PublicFunnelPageType | null): ResolvedPageMetadata | null {
  if (!page) return null;
  const metadata = page.metadata;
  if (metadata && typeof metadata.title === "string" && metadata.title.trim()) {
    return {
      title: metadata.title.trim(),
      description: typeof metadata.description === "string" ? metadata.description.trim() : "",
      lang: typeof metadata.lang === "string" && metadata.lang.trim() ? metadata.lang.trim() : "en",
      brandName:
        typeof metadata.brandName === "string" && metadata.brandName.trim() ? metadata.brandName.trim() : null,
    };
  }

  const rootProps = (page.puckData as { root?: { props?: Record<string, unknown> } } | undefined)?.root?.props;
  const title = typeof rootProps?.title === "string" ? rootProps.title.trim() : "";
  if (!title) return null;
  return {
    title,
    description: typeof rootProps?.description === "string" ? rootProps.description.trim() : "",
    lang: typeof rootProps?.lang === "string" && rootProps.lang.trim() ? rootProps.lang.trim() : "en",
    brandName: getBrandName(page.designSystemTokens),
  };
}

function getOrCreateId(storage: Storage, key: string) {
  const existing = storage.getItem(key);
  if (existing) return existing;
  const id =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `funnel-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  storage.setItem(key, id);
  return id;
}

function getUtmParams(): Record<string, string> {
  const params = new URLSearchParams(window.location.search);
  const utm: Record<string, string> = {};
  for (const [key, value] of params.entries()) {
    if (key.startsWith("utm_")) utm[key] = value;
  }
  return utm;
}

async function parsePublicError(resp: Response): Promise<string> {
  let raw: unknown;
  try {
    raw = await resp.clone().json();
  } catch {
    raw = await resp.text();
  }
  const detail = (raw as { detail?: unknown })?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  const message = (raw as { message?: unknown })?.message;
  if (typeof message === "string" && message.trim()) return message;
  if (typeof raw === "string" && raw.trim()) return raw;
  return resp.statusText || "Request failed";
}

function checkoutStatusFromLocation(): "success" | "cancel" | null {
  const checkoutStatus = new URL(window.location.href).searchParams.get("checkout");
  return checkoutStatus === "success" || checkoutStatus === "cancel" ? checkoutStatus : null;
}

function hasPaidEntryAttribution(): boolean {
  const params = new URLSearchParams(window.location.search);
  const clickIdKeys = ["fbclid", "gclid", "ttclid", "msclkid", "twclid", "li_fat_id"];
  for (const key of clickIdKeys) {
    const value = params.get(key);
    if (typeof value === "string" && value.trim()) {
      return true;
    }
  }

  const utmKeys = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
  for (const key of utmKeys) {
    const value = params.get(key);
    if (typeof value === "string" && value.trim()) {
      return true;
    }
  }
  return false;
}

function isSiteExperience(page: PublicFunnelPageType | null): boolean {
  if (!page) return false;
  return Boolean(page.pageTypeMap && Object.keys(page.pageTypeMap).length > 0);
}

function isB2CSiteExperience(page: PublicFunnelPageType | null, meta: PublicFunnelMeta | null): boolean {
  if (meta?.medusaRuntimeConfig) return true;
  const pageTypes = Object.values(page?.pageTypeMap || {});
  return pageTypes.some((pageType) =>
    [
      "store",
      "collection",
      "account_dashboard",
      "account_profile",
      "account_addresses",
      "account_orders",
      "account_order_detail",
      "order_confirmed",
      "order_transfer",
      "order_transfer_accept",
      "order_transfer_decline",
    ].includes(pageType),
  );
}

function resolveRequestedPageSlug(sitePath: string | undefined): string | undefined {
  const trimmed = (sitePath || "").replace(/^\//, "").trim();
  if (!trimmed) return undefined;
  if (!trimmed.includes("/")) {
    return /^[a-z]{2}$/i.test(trimmed) ? "home" : trimmed;
  }

  const parts = trimmed.split("/").filter(Boolean);
  const startIndex = /^[a-z]{2}$/i.test(parts[0] || "") ? 1 : 0;
  const routeParts = parts.slice(startIndex);

  if (routeParts.length === 0) return "home";
  if (routeParts[0] === "store") return "store";
  if (routeParts[0] === "collections") return "collection";
  if (routeParts[0] === "categories") return "category";
  if (routeParts[0] === "products") return "product";
  if (routeParts[0] === "cart") return "cart";
  if (routeParts[0] === "checkout") return "checkout";
  if (routeParts[0] === "policies" && routeParts[1] === "privacy-policy") return "privacy-policy";
  if (routeParts[0] === "policies" && routeParts[1] === "terms-of-service") return "terms-of-service";
  if (
    routeParts[0] === "policies" &&
    ["refund-policy", "returns-refunds-policy"].includes(routeParts[1] || "")
  ) {
    return "refund-policy";
  }
  if (routeParts[0] === "policies" && routeParts[1] === "shipping-policy") return "shipping-policy";
  if (
    (routeParts[0] === "policies" && ["contact", "contact-support"].includes(routeParts[1] || "")) ||
    routeParts[0] === "contact"
  ) {
    return "contact-support";
  }
  if (routeParts[0] === "account" && routeParts.length === 1) return "account";
  if (routeParts[0] === "account" && routeParts[1] === "profile") return "account/profile";
  if (routeParts[0] === "account" && routeParts[1] === "addresses") return "account/addresses";
  if (routeParts[0] === "account" && routeParts[1] === "orders" && routeParts[2] === "details") return "account/orders/details";
  if (routeParts[0] === "account" && routeParts[1] === "orders") return "account/orders";
  if (routeParts[0] === "order" && routeParts[2] === "confirmed") return "order/confirmed";
  if (routeParts[0] === "order" && routeParts[2] === "transfer" && routeParts[4] === "accept") return "order/transfer/accept";
  if (routeParts[0] === "order" && routeParts[2] === "transfer" && routeParts[4] === "decline") return "order/transfer/decline";
  if (routeParts[0] === "order" && routeParts[2] === "transfer") return "order/transfer";
  return trimmed;
}

export function PublicFunnelPage() {
  const routeParams = useParams();
  const routeProductSlug = routeParams.productSlug;
  const routeFunnelSlug = routeParams.funnelSlug;
  const routeSitePath = routeParams["*"];
  const [searchParams] = useSearchParams();
  const productSlug = routeProductSlug || undefined;
  const funnelSlug = routeFunnelSlug || undefined;
  const bundleMode = isStandaloneBundleMode();
  const navigate = useNavigate();
  const [meta, setMeta] = useState<PublicFunnelMeta | null>(null);
  const [page, setPage] = useState<PublicFunnelPageType | null>(null);
  const [pageLoading, setPageLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [commerce, setCommerce] = useState<PublicFunnelCommerce | null>(null);
  const [commerceError, setCommerceError] = useState<string | null>(null);
  const [siteCommerce, setSiteCommerce] = useState<SiteCommerceData | null>(null);
  const [siteCommerceLoading, setSiteCommerceLoading] = useState(false);
  const [siteCommerceError, setSiteCommerceError] = useState<string | null>(null);
  const sentPageViewRef = useRef<string | null>(null);
  const handledCheckoutReturnRef = useRef<string | null>(null);
  const effectiveSlug = useMemo(() => resolveRequestedPageSlug(routeSitePath || undefined), [routeSitePath]);
  const parsedRouteSitePath = useMemo(() => parseSitePath(routeSitePath || ""), [routeSitePath]);

  // Get product handle from query params for product detail pages
  const productHandle = searchParams.get("product") || undefined;
  const productId = searchParams.get("product_id") || undefined;
  const cartId = searchParams.get("cart_id") || undefined;
  const categoryHandle = searchParams.get("category") || undefined;

  const visitorId = useMemo(() => getOrCreateId(localStorage, "funnel_visitor_id"), []);
  const sessionId = useMemo(
    () => getOrCreateId(sessionStorage, `funnel_session_id:${productSlug || "unknown"}:${funnelSlug || "unknown"}`),
    [funnelSlug, productSlug],
  );
  const pageMetadata = useMemo(() => resolvePageMetadata(page), [page]);
  const normalizedPuckData = useMemo(() => {
    if (!page) return null;
    return normalizePuckData(page.puckData, { designSystemTokens: page.designSystemTokens ?? null });
  }, [page]);

  // Determine if this is a site experience
  const isSite = useMemo(() => isSiteExperience(page), [page]);

  useEffect(() => {
    ensureNoIndex();
  }, []);

  useEffect(() => {
    if (!productSlug || !funnelSlug) return;
    fetch(`${apiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/meta`)
      .then(async (resp) => {
        if (!resp.ok) return null;
        return (await resp.json()) as PublicFunnelMeta;
      })
      .then((m) => {
        setMeta(m);
        setMedusaRuntimeConfig(m?.medusaRuntimeConfig ?? null);
      })
      .catch(() => setMeta(null));
  }, [funnelSlug, productSlug]);

  useEffect(() => {
    const defaultCountryCode = meta?.medusaRuntimeConfig?.defaultCountryCode;
    if (!defaultCountryCode || !productSlug || !funnelSlug || !routeSitePath) return;
    if (parsedRouteSitePath.countryCode) return;

    navigate(
      `${buildPublicFunnelPath({
        productSlug,
        funnelSlug,
        bundleMode,
        sitePath: `${defaultCountryCode}/${routeSitePath.replace(/^\//, "")}`,
      })}${window.location.search}${window.location.hash}`,
      { replace: true },
    );
  }, [bundleMode, funnelSlug, meta, navigate, parsedRouteSitePath.countryCode, productSlug, routeSitePath]);

  // Fetch legacy commerce data for non-site funnels
  useEffect(() => {
    if (!productSlug || !funnelSlug || !page) return;
    if (isSite) {
      setCommerce(null);
      setCommerceError(null);
      return; // Skip legacy commerce for site experiences once the page type is known
    }
    setCommerce(null);
    setCommerceError(null);
    fetch(`${apiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/commerce`)
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(await parsePublicError(resp));
        }
        return (await resp.json()) as PublicFunnelCommerce;
      })
      .then((data) => setCommerce(data))
      .catch((err: unknown) => {
        setCommerceError(err instanceof Error ? err.message : "Unable to load commerce data");
      });
  }, [funnelSlug, page, productSlug, isSite]);

  // Fetch site commerce data for site experiences
  useEffect(() => {
    if (!productSlug || !funnelSlug) return;
    if (!isSite) {
      return;
    }
    if (isB2CSiteExperience(page, meta)) {
      setSiteCommerce(null);
      setSiteCommerceLoading(false);
      setSiteCommerceError(null);
      return;
    }
    setSiteCommerceLoading(true);
    setSiteCommerceError(null);

    const params = new URLSearchParams();
    if (productHandle) params.set("product_handle", productHandle);
    if (productId) params.set("product_id", productId);
    if (cartId) params.set("cart_id", cartId);
    if (categoryHandle) params.set("category_handle", categoryHandle);

    const queryString = params.toString();
    const url = `${apiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/site/commerce${queryString ? `?${queryString}` : ""}`;
    fetch(url)
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(await parsePublicError(resp));
        }
        return (await resp.json()) as SiteCommerceData;
      })
      .then((data) => {
        if (data.errors && data.errors.length > 0) {
          console.warn("Site commerce data has errors:", data.errors);
        }
        setSiteCommerce(data);
      })
      .catch((err: unknown) => {
        setSiteCommerceError(err instanceof Error ? err.message : "Unable to load site commerce data");
      })
      .finally(() => {
        setSiteCommerceLoading(false);
      });
  }, [cartId, categoryHandle, funnelSlug, isSite, meta, page, productHandle, productId, productSlug]);

  useEffect(() => {
    if (!productSlug || !funnelSlug || !effectiveSlug) {
      return;
    }
    setError(null);
    setPageLoading(true);
    const encodedSlugPath = effectiveSlug
      .split("/")
      .filter(Boolean)
      .map((segment) => encodeURIComponent(segment))
      .join("/");
    const fetchUrl = `${apiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/pages/${encodedSlugPath}`;
    fetch(fetchUrl)
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(await parsePublicError(resp));
        }
        return (await resp.json()) as PublicFunnelPageType;
      })
      .then((data) => {
        if (data.redirectToSlug) {
          navigate(
            buildPublicFunnelPath({
              productSlug,
              funnelSlug,
              slug: data.redirectToSlug,
              bundleMode,
            }),
            { replace: true },
          );
          return;
        }
        setPage(data);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unable to load funnel page");
      })
      .finally(() => {
        setPageLoading(false);
      });
  }, [bundleMode, effectiveSlug, funnelSlug, navigate, productSlug]);

  const trackEvent = async (event: RuntimeTrackingEvent) => {
    if (!page) return;
    const metaPixelId = page.tracking?.provider === "meta" ? page.tracking.metaPixelId || null : null;
    const mappedMetaEvents = mapRuntimeEventToMetaPixelEvents(event);
    const payload = {
      events: [
        {
          eventType: event.eventType,
          publicationId: page.publicationId,
          pageId: page.pageId,
          visitorId,
          sessionId,
          path: window.location.pathname + window.location.search,
          referrer: document.referrer || undefined,
          utm: getUtmParams(),
          props: {
            fromPageId: page.pageId,
            slug: page.slug,
            pageStage: page.stage,
            ...event.props,
          },
        },
      ],
    };
    for (const mappedMetaEvent of mappedMetaEvents) {
      trackMetaPixelEvent(
        metaPixelId,
        mappedMetaEvent.eventName,
        mappedMetaEvent.params,
        mappedMetaEvent.method,
      );
    }
    try {
      await fetch(`${apiBaseUrl}/public/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true,
      });
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (!page) return;
    if (page.stage === "sales" && checkoutStatusFromLocation()) return;
    if (sentPageViewRef.current === page.pageId) return;
    sentPageViewRef.current = page.pageId;
    void trackEvent(pageViewEventForStage(page.stage, { pageStage: page.stage }));
  }, [page]);

  useEffect(() => {
    if (!page) return;
    if (!hasPaidEntryAttribution()) return;
    const key = `funnel_entered:${funnelSlug}:${sessionId}`;
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "1");
    void trackEvent({
      eventType: "Entered Funnel",
      props: {
        pageStage: page.stage,
      },
    });
  }, [funnelSlug, page, sessionId]);

  useEffect(() => {
    if (!page) return;
    setPageMetadata(pageMetadata);
    return () => {
      clearManagedMetaTags();
    };
  }, [page, pageMetadata]);

  useEffect(() => {
    setPageFavicon(pageMetadata?.brandName ?? null);
    return () => {
      clearManagedFavicons();
    };
  }, [pageMetadata]);

  useEffect(() => {
    const metaPixelId = page?.tracking?.provider === "meta" ? page.tracking.metaPixelId || null : null;
    ensureMetaPixel(metaPixelId);
  }, [page?.tracking?.metaPixelId, page?.tracking?.provider]);

  useEffect(() => {
    if (!page) return;

    const checkoutStatus = checkoutStatusFromLocation();
    if (!checkoutStatus) {
      return;
    }

    const pendingPurchaseKey = pendingMetaPurchaseStorageKey(sessionId, funnelSlug);
    const pendingPurchase = pendingPurchaseKey ? readPendingMetaPurchase(sessionStorage, pendingPurchaseKey) : null;
    const checkoutMarker = pendingPurchase
      ? `${checkoutStatus}:${pendingPurchase.createdAt}`
      : `${checkoutStatus}:${sessionId}:${page.pageId}`;
    if (handledCheckoutReturnRef.current === checkoutMarker) {
      return;
    }
    handledCheckoutReturnRef.current = checkoutMarker;

    const metaPixelId = page.tracking?.provider === "meta" ? page.tracking.metaPixelId || null : null;
    if (checkoutStatus === "success") {
      void trackEvent(
        pageViewEventForStage("thank_you", {
          pageStage: "thank_you",
          checkoutStatus,
          provider: pendingPurchase?.provider || null,
        }),
      );
      if (pendingPurchase?.provider === "stripe") {
        trackMetaPixelEvent(metaPixelId, "Purchase", buildPurchaseEventParams(pendingPurchase));
      }
    }

    if (pendingPurchaseKey) {
      clearPendingMetaPurchase(sessionStorage, pendingPurchaseKey);
    }
    window.history.replaceState(window.history.state, "", clearCheckoutQueryParam(window.location.href));
  }, [funnelSlug, page, sessionId]);

  if (!productSlug || !funnelSlug) {
    return <div className="min-h-screen bg-surface p-6 text-sm text-content-muted">Missing public funnel path.</div>;
  }

  if (error) {
    return (
      <div className="min-h-screen bg-surface p-6 text-sm text-content-muted">
        This funnel page is unavailable. {error}
      </div>
    );
  }

  if (!page) {
    return <div className="min-h-screen bg-surface p-6 text-sm text-content-muted">Loading page…</div>;
  }

  const useB2CRuntime = isB2CSiteExperience(page, meta);

  // Site experience: wrap with CommerceRuntimeProvider
  if (isSite) {
    return (
      <div className="min-h-screen bg-surface" data-public-funnel-page="true">
        {pageLoading || siteCommerceLoading ? (
          <div className="fixed inset-x-0 top-0 z-[120] h-0.5 bg-content/80 animate-pulse" aria-hidden="true" />
        ) : null}
        <FunnelRuntimeProvider
          value={{
            productSlug,
            funnelSlug,
            pageMap: page.pageMap,
            pageStageMap: page.pageStageMap,
            pageTypeMap: page.pageTypeMap,
            bundleMode,
            entrySlug: meta?.entrySlug ?? null,
            pageStage: page.stage,
            trackEvent,
            commerce,
            commerceError,
            pageId: page.pageId,
            nextPageId: page.nextPageId ?? null,
            visitorId,
            sessionId,
          }}
        >
          {useB2CRuntime ? (
            <B2CRuntimeProvider
              siteFamily={siteCommerce?.siteFamily || "medusa-b2c-starter"}
              siteName={pageMetadata?.brandName || pageMetadata?.title || null}
              initialCountryCode={parsedRouteSitePath.countryCode || undefined}
            >
              <DesignSystemProvider tokens={page.designSystemTokens}>
                <Render
                  key={page.pageId}
                  config={runtimeConfig}
                  data={(normalizedPuckData ?? page.puckData) as unknown as Data}
                />
              </DesignSystemProvider>
            </B2CRuntimeProvider>
          ) : (
            <CommerceRuntimeProvider
              productSlug={productSlug}
              funnelSlug={funnelSlug}
              apiBaseUrl={apiBaseUrl}
              initialRegions={siteCommerce?.regions || []}
              initialProducts={siteCommerce?.products || []}
              initialCollections={siteCommerce?.collections || []}
              initialCategories={siteCommerce?.categories || []}
              initialCurrentProduct={siteCommerce?.currentProduct || null}
              initialCurrentCategory={siteCommerce?.currentCategory || null}
              siteFamily={siteCommerce?.siteFamily || null}
              commerceProvider={siteCommerce?.commerceProvider || null}
              storeName={siteCommerce?.storeName || null}
            >
              <DesignSystemProvider tokens={page.designSystemTokens}>
                <Render
                  key={page.pageId}
                  config={runtimeConfig}
                  data={(normalizedPuckData ?? page.puckData) as unknown as Data}
                />
              </DesignSystemProvider>
            </CommerceRuntimeProvider>
          )}
        </FunnelRuntimeProvider>
      </div>
    );
  }

  // Non-site funnel: use existing FunnelRuntimeProvider only
  return (
    <div className="min-h-screen bg-surface" data-public-funnel-page="true">
      {pageLoading ? <div className="fixed inset-x-0 top-0 z-[120] h-0.5 bg-content/80 animate-pulse" aria-hidden="true" /> : null}
      <FunnelRuntimeProvider
        value={{
          productSlug,
          funnelSlug,
          pageMap: page.pageMap,
          pageStageMap: page.pageStageMap,
          bundleMode,
          entrySlug: meta?.entrySlug ?? null,
          pageStage: page.stage,
          trackEvent,
          commerce,
          commerceError,
          pageId: page.pageId,
          nextPageId: page.nextPageId ?? null,
          visitorId,
          sessionId,
        }}
      >
        <DesignSystemProvider tokens={page.designSystemTokens}>
          <Render
            key={page.pageId}
            config={runtimeConfig}
            data={(normalizedPuckData ?? page.puckData) as unknown as Data}
          />
        </DesignSystemProvider>
      </FunnelRuntimeProvider>
    </div>
  );
}
