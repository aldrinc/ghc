import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type {
  ImportedHtmlInstrumentationManifest,
  PublicFunnelMeta,
  PublicFunnelPage as PublicFunnelPageType,
} from "@/types/funnels";
import type { PublicFunnelCommerce } from "@/types/commerce";
import {
  buildPublicFunnelPath,
  getStandaloneDefaultFunnelSlug,
  getStandalonePreloadedFunnelData,
  isStandaloneBundleMode,
  normalizeRouteToken,
  resolvePublicApiBaseUrl,
} from "@/funnels/runtimeRouting";
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
import { PublicFunnelShellMessage } from "@/pages/public/publicFunnelShell";

const apiBaseUrl = resolvePublicApiBaseUrl();
const managedFaviconAttr = "data-mos-managed-favicon";
const managedMetaAttr = "data-mos-managed-meta";
const PublicFunnelPuckRenderer = lazy(() => import("./PublicFunnelPuckRenderer"));
const PublicImportedHtmlRenderer = lazy(() => import("./PublicImportedHtmlRenderer"));

type ResolvedPageMetadata = {
  title: string;
  description: string;
  lang: string;
  brandName: string | null;
};

type StandaloneImportedHtmlPayload = {
  htmlDocument: string;
  instrumentationManifest: ImportedHtmlInstrumentationManifest | null;
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

function resolveStandaloneImportedHtmlPayload(
  page: PublicFunnelPageType | null,
): StandaloneImportedHtmlPayload | null {
  if (!page || !isRecord(page.puckData)) return null;
  const content = Array.isArray(page.puckData.content) ? page.puckData.content : null;
  if (!content || content.length !== 1) return null;
  const block = content[0];
  if (!isRecord(block) || block.type !== "ImportedHtmlDocument") return null;
  const props = isRecord(block.props) ? block.props : null;
  if (!props) return null;
  const htmlDocument = typeof props.htmlDocument === "string" ? props.htmlDocument.trim() : "";
  if (!htmlDocument) return null;
  const manifest = isRecord(props.instrumentationManifest)
    ? (props.instrumentationManifest as ImportedHtmlInstrumentationManifest)
    : null;
  return {
    htmlDocument,
    instrumentationManifest: manifest,
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

export function PublicFunnelPage() {
  const { productSlug: routeProductSlug, funnelSlug: routeFunnelSlug, slug: routeSlug } = useParams();
  const productSlug = routeProductSlug || undefined;
  const bundleMode = isStandaloneBundleMode();
  const funnelSlug = routeFunnelSlug || (bundleMode ? getStandaloneDefaultFunnelSlug() || undefined : undefined);
  const navigate = useNavigate();
  const effectiveSlug = routeSlug || undefined;
  const preloadedFunnel = useMemo(
    () =>
      bundleMode
        ? getStandalonePreloadedFunnelData({
            productSlug,
            funnelSlug,
          })
        : null,
    [bundleMode, funnelSlug, productSlug],
  );
  const preloadedPage = useMemo(() => {
    const normalizedSlug = normalizeRouteToken(effectiveSlug);
    if (!normalizedSlug) return null;
    return preloadedFunnel?.pages?.[normalizedSlug] ?? null;
  }, [effectiveSlug, preloadedFunnel]);
  const [meta, setMeta] = useState<PublicFunnelMeta | null>(preloadedFunnel?.meta ?? null);
  const [page, setPage] = useState<PublicFunnelPageType | null>(preloadedPage);
  const [error, setError] = useState<string | null>(null);
  const [commerce, setCommerce] = useState<PublicFunnelCommerce | null>(preloadedFunnel?.commerce ?? null);
  const [commerceError, setCommerceError] = useState<string | null>(null);
  const sentPageViewRef = useRef<string | null>(null);
  const handledCheckoutReturnRef = useRef<string | null>(null);

  const visitorId = useMemo(() => getOrCreateId(localStorage, "funnel_visitor_id"), []);
  const sessionId = useMemo(
    () => getOrCreateId(sessionStorage, `funnel_session_id:${productSlug || "unknown"}:${funnelSlug || "unknown"}`),
    [funnelSlug, productSlug],
  );
  const standaloneImportedHtmlPayload = useMemo(
    () => (bundleMode ? resolveStandaloneImportedHtmlPayload(page) : null),
    [bundleMode, page],
  );
  const standalonePagePathById = useMemo(() => {
    if (!bundleMode || !page || !productSlug || !funnelSlug) return {};
    return Object.fromEntries(
      Object.entries(page.pageMap).map(([pageId, slug]) => [
        pageId,
        buildPublicFunnelPath({
          productSlug,
          funnelSlug,
          slug,
          bundleMode,
        }),
      ]),
    );
  }, [bundleMode, funnelSlug, page, productSlug]);

  useEffect(() => {
    ensureNoIndex();
  }, []);

  useEffect(() => {
    if (!productSlug || !funnelSlug) return;
    if (preloadedFunnel?.meta) {
      setMeta(preloadedFunnel.meta);
      return;
    }
    fetch(`${apiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/meta`)
      .then(async (resp) => {
        if (!resp.ok) return null;
        return (await resp.json()) as PublicFunnelMeta;
      })
      .then((m) => setMeta(m))
      .catch(() => setMeta(null));
  }, [funnelSlug, preloadedFunnel?.meta, productSlug]);

  useEffect(() => {
    if (!productSlug || !funnelSlug || !page) return;
    if (preloadedFunnel?.commerce) {
      setCommerce(preloadedFunnel.commerce);
      setCommerceError(null);
      return;
    }
    if (bundleMode && standaloneImportedHtmlPayload) {
      setCommerce(null);
      setCommerceError(null);
      return;
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
  }, [bundleMode, funnelSlug, page, preloadedFunnel?.commerce, productSlug, standaloneImportedHtmlPayload]);

  useEffect(() => {
    if (!productSlug || !funnelSlug || !effectiveSlug) return;
    setError(null);
    if (preloadedPage) {
      setPage(preloadedPage);
      return;
    }
    setPage(null);
    fetch(
      `${apiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/pages/${encodeURIComponent(effectiveSlug)}`,
    )
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(await parsePublicError(resp));
        }
        return (await resp.json()) as PublicFunnelPageType;
      })
      .then((data) => {
        if (data.redirectToSlug) {
          const redirectPath = buildPublicFunnelPath({
            productSlug,
            funnelSlug,
            slug: data.redirectToSlug,
            bundleMode,
          });
          navigate(
            `${redirectPath}${window.location.search}${window.location.hash}`,
            { replace: true },
          );
          return;
        }
        setPage(data);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unable to load funnel page");
      });
  }, [bundleMode, effectiveSlug, funnelSlug, navigate, preloadedPage, productSlug]);

  const trackEvent = (event: RuntimeTrackingEvent) => {
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
      void fetch(`${apiBaseUrl}/public/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(() => {
        // ignore
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
    setPageMetadata(resolvePageMetadata(page));
    return () => {
      clearManagedMetaTags();
    };
  }, [page]);

  useEffect(() => {
    setPageFavicon(resolvePageMetadata(page)?.brandName ?? null);
    return () => {
      clearManagedFavicons();
    };
  }, [page]);

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
    return <PublicFunnelShellMessage>Missing public funnel path.</PublicFunnelShellMessage>;
  }

  if (error) {
    return <PublicFunnelShellMessage>This funnel page is unavailable. {error}</PublicFunnelShellMessage>;
  }

  if (!page) {
    return <PublicFunnelShellMessage>Loading page…</PublicFunnelShellMessage>;
  }

  if (standaloneImportedHtmlPayload) {
    if (!standaloneImportedHtmlPayload.instrumentationManifest) {
      return <PublicFunnelShellMessage>Imported HTML page is missing a valid instrumentation manifest.</PublicFunnelShellMessage>;
    }
    return (
      <Suspense fallback={<PublicFunnelShellMessage>Loading page…</PublicFunnelShellMessage>}>
        <PublicImportedHtmlRenderer
          page={page}
          productSlug={productSlug}
          funnelSlug={funnelSlug}
          visitorId={visitorId}
          sessionId={sessionId}
          htmlDocument={standaloneImportedHtmlPayload.htmlDocument}
          instrumentationManifest={standaloneImportedHtmlPayload.instrumentationManifest}
          variants={commerce?.product?.variants ?? []}
          pagePathById={standalonePagePathById}
          pageStageById={page.pageStageMap}
        />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<PublicFunnelShellMessage>Loading page…</PublicFunnelShellMessage>}>
      <PublicFunnelPuckRenderer
        page={page}
        meta={meta}
        productSlug={productSlug}
        funnelSlug={funnelSlug}
        bundleMode={bundleMode}
        trackEvent={trackEvent}
        commerce={commerce}
        commerceError={commerceError}
        visitorId={visitorId}
        sessionId={sessionId}
      />
    </Suspense>
  );
}
