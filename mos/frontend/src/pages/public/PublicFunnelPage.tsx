import { Render } from "@measured/puck";
import type { Data } from "@measured/puck";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { PublicFunnelMeta, PublicFunnelPage as PublicFunnelPageType } from "@/types/funnels";
import type { PublicFunnelCommerce } from "@/types/commerce";
import { createFunnelPuckConfig, FunnelRuntimeProvider } from "@/funnels/puckConfig";
import { normalizePuckData } from "@/funnels/puckData";
import { buildPublicFunnelPath, getStandalonePublicId, isStandaloneRootModeForPublicId } from "@/funnels/runtimeRouting";
import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";
const runtimeConfig = createFunnelPuckConfig();

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

function setPageMetadata(title?: string, description?: string) {
  if (typeof title === "string" && title.trim()) {
    document.title = title.trim();
  }
  if (typeof description === "string") {
    const name = "description";
    const existing = document.querySelector(`meta[name="${name}"]`);
    if (existing) {
      existing.setAttribute("content", description);
      return;
    }
    const meta = document.createElement("meta");
    meta.setAttribute("name", name);
    meta.setAttribute("content", description);
    document.head.appendChild(meta);
  }
}

function getOrCreateId(storage: Storage, key: string) {
  const existing = storage.getItem(key);
  if (existing) return existing;
  const id = crypto.randomUUID();
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

export function PublicFunnelPage() {
  const { publicId: routePublicId, slug: routeSlug } = useParams();
  const standalonePublicId = getStandalonePublicId();
  const publicId = routePublicId || standalonePublicId || undefined;
  const rootMode = isStandaloneRootModeForPublicId(publicId);
  const navigate = useNavigate();
  const [meta, setMeta] = useState<PublicFunnelMeta | null>(null);
  const [page, setPage] = useState<PublicFunnelPageType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [commerce, setCommerce] = useState<PublicFunnelCommerce | null>(null);
  const [commerceError, setCommerceError] = useState<string | null>(null);
  const sentPageViewRef = useRef<string | null>(null);
  const effectiveSlug = routeSlug || (rootMode ? meta?.entrySlug : undefined);

  const visitorId = useMemo(() => getOrCreateId(localStorage, "funnel_visitor_id"), []);
  const sessionId = useMemo(
    () => getOrCreateId(sessionStorage, `funnel_session_id:${publicId || "unknown"}`),
    [publicId],
  );
  const normalizedPuckData = useMemo(() => {
    if (!page) return null;
    return normalizePuckData(page.puckData, { designSystemTokens: page.designSystemTokens ?? null });
  }, [page]);

  useEffect(() => {
    ensureNoIndex();
  }, []);

  useEffect(() => {
    if (!publicId) return;
    fetch(`${apiBaseUrl}/public/funnels/${publicId}/meta`)
      .then(async (resp) => {
        if (!resp.ok) return null;
        return (await resp.json()) as PublicFunnelMeta;
      })
      .then((m) => setMeta(m))
      .catch(() => setMeta(null));
  }, [publicId]);

  useEffect(() => {
    if (!publicId) return;
    setCommerce(null);
    setCommerceError(null);
    fetch(`${apiBaseUrl}/public/funnels/${publicId}/commerce`)
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
  }, [publicId]);

  useEffect(() => {
    if (!publicId || !effectiveSlug) return;
    setError(null);
    setPage(null);
    fetch(`${apiBaseUrl}/public/funnels/${publicId}/pages/${encodeURIComponent(effectiveSlug)}`)
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
              publicId,
              slug: data.redirectToSlug,
              entrySlug: meta?.entrySlug,
              rootMode,
            }),
            { replace: true },
          );
          return;
        }
        setPage(data);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unable to load funnel page");
      });
  }, [effectiveSlug, meta?.entrySlug, navigate, publicId, rootMode]);

  const trackEvent = async (event: { eventType: string; props?: Record<string, unknown> }) => {
    if (!page) return;
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
            ...event.props,
          },
        },
      ],
    };
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
    if (sentPageViewRef.current === page.pageId) return;
    sentPageViewRef.current = page.pageId;
    trackEvent({ eventType: "page_view" });
  }, [page]);

  useEffect(() => {
    if (!page) return;
    const rootProps = (page.puckData as { root?: { props?: Record<string, unknown> } } | undefined)?.root?.props;
    if (!rootProps) return;
    const title = typeof rootProps.title === "string" ? rootProps.title : undefined;
    const description = typeof rootProps.description === "string" ? rootProps.description : undefined;
    setPageMetadata(title, description);
  }, [page]);

  useEffect(() => {
    if (!page || !meta) return;
    if (page.slug !== meta.entrySlug) return;
    const key = `funnel_entered:${meta.publicId}:${sessionId}`;
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "1");
    trackEvent({ eventType: "funnel_enter" });
  }, [meta, page, sessionId]);

  if (!publicId) {
    return <div className="min-h-screen bg-surface p-6 text-sm text-content-muted">Missing public id.</div>;
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

  return (
    <div className="min-h-screen bg-surface">
      <FunnelRuntimeProvider
        value={{
          publicId,
          pageMap: page.pageMap,
          rootMode,
          entrySlug: meta?.entrySlug ?? null,
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
          <Render config={runtimeConfig} data={(normalizedPuckData ?? page.puckData) as unknown as Data} />
        </DesignSystemProvider>
      </FunnelRuntimeProvider>
    </div>
  );
}
