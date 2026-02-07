import { useEffect, useMemo, useState } from "react";
import { useLatestArtifact } from "@/api/artifacts";
import { LibraryCard } from "@/components/library/LibraryCard";
import { normalizeBreakdownAdToLibraryItem, normalizeFacebookAdToLibraryItem } from "@/lib/library";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import type { LibraryItem } from "@/types/library";
import { useAdsApi } from "@/api/ads";
import { AdsIngestionRetryCallout } from "@/components/ads/AdsIngestionRetryCallout";

function LoadingGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div
          key={idx}
          className="ds-card ds-card--md flex flex-col gap-3 shadow-none animate-pulse"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="h-3 w-24 rounded bg-muted" />
            <div className="h-4 w-10 rounded-full bg-muted" />
          </div>
          <div className="h-40 w-full rounded-lg bg-muted" />
          <div className="space-y-2">
            <div className="h-3 w-3/4 rounded bg-muted" />
            <div className="h-3 w-full rounded bg-muted" />
            <div className="h-3 w-2/3 rounded bg-muted" />
          </div>
          <div className="flex items-center justify-between text-xs text-content-muted">
            <div className="h-3 w-20 rounded bg-muted" />
            <div className="h-3 w-12 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

function parseAdsContext(raw: unknown) {
  if (!raw) return null;
  let parsed: any = raw;
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (typeof parsed !== "object" || !parsed) return null;
  // unwrap nested shapes: { ads_context: {...} }
  if ((parsed as any).ads_context) parsed = (parsed as any).ads_context;
  if ((parsed as any).adsContext) parsed = (parsed as any).adsContext;
  return parsed as Record<string, unknown>;
}

export function AdsPanel() {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { listAds } = useAdsApi();
  const { latest: canonArtifact, isLoading, error } = useLatestArtifact({
    clientId: workspace?.id,
    productId: product?.id,
    type: "client_canon",
  });
  const [savedIds, setSavedIds] = useState<Record<string, boolean>>({});
  const [apiAds, setApiAds] = useState<any[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [apiLoading, setApiLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!workspace?.id || !product?.id) {
      setApiAds([]);
      setApiError(null);
      setApiLoading(false);
      return;
    }
    setApiLoading(true);
    listAds({ clientId: workspace.id, productId: product.id, limit: 120 })
      .then((resp) => {
        if (cancelled) return;
        const payload = (resp as any)?.ads || resp || [];
        setApiAds(Array.isArray(payload) ? payload : []);
        setApiError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setApiAds([]);
        setApiError(err?.message || "Failed to load ads");
      })
      .finally(() => {
        if (cancelled) return;
        setApiLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [listAds, product?.id, workspace?.id]);

  const adsContext = useMemo(() => {
    if (!canonArtifact?.data) return null;
    const data: any = canonArtifact.data;
    const research = data?.precanon_research || data?.precanonResearch;
    return parseAdsContext(research?.ads_context || research?.adsContext);
  }, [canonArtifact?.data]);

  const contextAds = useMemo(() => {
    return Array.isArray((adsContext as any)?.ads) ? (adsContext as any).ads : [];
  }, [adsContext]);

  const breakdownAds = useMemo(() => {
    return adsContext?.creative_breakdowns?.ads || [];
  }, [adsContext]);

  const items = useMemo<LibraryItem[]>(() => {
    const baseAds = apiAds.length ? apiAds : [];
    const normalized: LibraryItem[] = [];
    if (Array.isArray(baseAds)) {
      normalized.push(
        ...baseAds.map((ad: any) =>
          ad?.snapshot || ad?.publisher_platform
            ? normalizeFacebookAdToLibraryItem(ad)
            : normalizeBreakdownAdToLibraryItem(ad),
        ),
      );
    }
    if (!baseAds.length && Array.isArray(contextAds)) {
      normalized.push(
        ...contextAds.map((ad: any) =>
          ad?.snapshot || ad?.publisher_platform
            ? normalizeFacebookAdToLibraryItem(ad)
            : normalizeBreakdownAdToLibraryItem(ad),
        ),
      );
    }
    if (!baseAds.length && Array.isArray(breakdownAds)) {
      normalized.push(...breakdownAds.map((ad: any) => normalizeBreakdownAdToLibraryItem(ad)));
    }
    // Remove dupes by id
    const seen = new Set<string>();
    return normalized.filter((item) => {
      const key = item.id;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [apiAds, breakdownAds, contextAds]);

  const handleSave = (item: LibraryItem) => {
    // TODO: wire to backend save endpoint when available.
    setSavedIds((prev) => ({ ...prev, [item.id]: true }));
  };

  const handleOpenSource = (item: LibraryItem) => {
    const url = item.destinationUrl || item.media[0]?.url;
    if (url) window.open(url, "_blank", "noreferrer");
  };

  const handleCopyLink = async (item: LibraryItem) => {
    const url = item.destinationUrl || item.media[0]?.url;
    if (!url) return;
    try {
      await navigator?.clipboard?.writeText(url);
    } catch {
      // ignore clipboard failures
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-xl font-semibold text-content">Ads</h2>
          <p className="text-sm text-content-muted">Raw ads you’ve ingested (with full media + metadata).</p>
        </div>
      </div>
      <AdsIngestionRetryCallout clientId={workspace?.id} productId={product?.id} />
      {!workspace && (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          Select a workspace to view ingested ads.
        </div>
      )}
      {workspace && !product && (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          Select a product to view ingested ads.
        </div>
      )}
      {(apiError || error) && (
        <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {apiError || (error as any)?.message || "Failed to load ads"}
        </div>
      )}
      {(apiLoading || isLoading) && <LoadingGrid />}
      {!apiLoading && !isLoading && workspace && product && items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <LibraryCard
              key={item.id}
              item={item}
              saved={savedIds[item.id]}
              onSave={handleSave}
              onOpenSource={handleOpenSource}
              onCopyLink={handleCopyLink}
            />
          ))}
        </div>
      )}
      {!apiLoading && !isLoading && workspace && product && items.length === 0 && !apiError && !error && (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          No ads available yet. Run ingestion to populate this tab.
        </div>
      )}
    </div>
  );
}
