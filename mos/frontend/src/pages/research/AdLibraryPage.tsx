import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { useLatestArtifact } from "@/api/artifacts";
import { useClientSwipes } from "@/api/swipes";
import { LibraryCard } from "@/components/library/LibraryCard";
import { Callout } from "@/components/ui/callout";
import { normalizeBreakdownAdToLibraryItem, normalizeFacebookAdToLibraryItem } from "@/lib/library";
import type { LibraryItem } from "@/types/library";
import { useAdsApi } from "@/api/ads";

function LoadingGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div
          key={idx}
          className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4 shadow-sm animate-pulse"
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

function parseAdsContext(raw: unknown): any | null {
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
  if (parsed.ads_context) parsed = parsed.ads_context;
  if (parsed.adsContext) parsed = parsed.adsContext;
  return parsed;
}

export function AdLibraryPage() {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { listAds } = useAdsApi();
  const { latest: canonArtifact, isLoading } = useLatestArtifact({
    clientId: workspace?.id,
    productId: product?.id,
    type: "client_canon",
  });
  const { data: swipes = [], isLoading: swipesLoading } = useClientSwipes(workspace?.id);
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
    listAds({ clientId: workspace.id, productId: product.id, limit: 200 })
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
    const rawResearch = (canonArtifact?.data as any)?.precanon_research || (canonArtifact?.data as any)?.precanonResearch;
    return parseAdsContext(rawResearch?.ads_context || rawResearch?.adsContext);
  }, [canonArtifact?.data]);

  const creativeBreakdowns = adsContext?.creative_breakdowns;
  const contextAds = useMemo(() => (Array.isArray((adsContext as any)?.ads) ? (adsContext as any).ads : []), [adsContext]);
  const breakdownAds = creativeBreakdowns?.ads as any[] | undefined;

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
    const seen = new Set<string>();
    return normalized.filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  }, [apiAds, breakdownAds, contextAds]);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Ad Library" description="Select a workspace to view ingested ads." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a workspace from the sidebar.
        </div>
      </div>
    );
  }
  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Ad Library" description="Select a product to view ingested ads." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a product from the header to view ads.
        </div>
      </div>
    );
  }

  const breakdownSummary = creativeBreakdowns?.summary;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Ad Library"
        description={`Ads ingested during onboarding for ${product.title}, plus saved swipes for this workspace.`}
      />

      {apiError ? (
        <Callout variant="danger" size="sm" title="Failed to load ads">
          {apiError}
        </Callout>
      ) : null}

      {(apiLoading || isLoading) && <LoadingGrid />}
      {!apiLoading && !isLoading && !creativeBreakdowns && !items.length ? (
        <div className="ds-card ds-card--md ds-card--empty text-sm shadow-none">
          No ads ingestion context found. Run onboarding to populate the ad library.
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="ds-card ds-card--sm bg-surface-2 shadow-none">
              <div className="text-xs text-content-muted uppercase">Total ads</div>
              <div className="text-lg font-semibold text-content">{breakdownSummary?.total_ads ?? items.length}</div>
            </div>
            <div className="ds-card ds-card--sm bg-surface-2 shadow-none">
              <div className="text-xs text-content-muted uppercase">Completed</div>
              <div className="text-lg font-semibold text-content">
                {breakdownSummary?.succeeded ??
                  breakdownSummary?.["SUCCEEDED"] ??
                  breakdownSummary?.completed ??
                  items.length}
              </div>
            </div>
            <div className="ds-card ds-card--sm bg-surface-2 shadow-none">
              <div className="text-xs text-content-muted uppercase">Queued/Running</div>
              <div className="text-lg font-semibold text-content">
                {(breakdownSummary?.queued ?? breakdownSummary?.["QUEUED"] ?? 0) +
                  (breakdownSummary?.running ?? breakdownSummary?.["RUNNING"] ?? 0)}
              </div>
            </div>
            <div className="ds-card ds-card--sm bg-surface-2 shadow-none">
              <div className="text-xs text-content-muted uppercase">Failed/Missing</div>
              <div className="text-lg font-semibold text-content">
                {(breakdownSummary?.failed ?? breakdownSummary?.["FAILED"] ?? 0) + (breakdownSummary?.missing ?? 0)}
              </div>
            </div>
          </div>

          {items.length ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((item) => (
                <LibraryCard
                  key={item.id}
                  item={item}
                  saved={savedIds[item.id]}
                  onSave={() => setSavedIds((prev) => ({ ...prev, [item.id]: true }))}
                  onOpenSource={(it) => {
                    const url = it.destinationUrl || it.media[0]?.url;
                    if (url) window.open(url, "_blank", "noreferrer");
                  }}
                  onCopyLink={async (it) => {
                    const url = it.destinationUrl || it.media[0]?.url;
                    if (!url) return;
                    try {
                      await navigator?.clipboard?.writeText(url);
                    } catch {
                      /* noop */
                    }
                  }}
                />
              ))}
            </div>
          ) : (
            <div className="ds-card ds-card--md ds-card--empty text-sm shadow-none">No ads available yet.</div>
          )}
        </div>
      )}

      <div className="ds-card ds-card--md p-0 border border-border shadow-none bg-surface">
        <div className="border-b border-border px-4 py-3">
          <div className="text-sm font-semibold text-content">Saved swipes</div>
          <div className="text-xs text-content-muted">Manually curated examples tied to this workspace.</div>
        </div>
        {swipesLoading ? (
          <div className="p-4 text-sm text-content-muted">Loading swipes…</div>
        ) : swipes.length ? (
          <div className="divide-y divide-border">
            {swipes.map((swipe) => (
              <div key={swipe.id} className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-content">
                    {swipe.custom_title || swipe.custom_body || "Swipe"}
                  </div>
                  <div className="text-xs text-content-muted font-mono">{swipe.id.slice(0, 6)}…</div>
                </div>
                <div className="mt-1 text-xs text-content-muted">
                  {swipe.custom_channel || swipe.custom_format || swipe.company_swipe_id || "Channel not set"}
                </div>
                {swipe.tags?.length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {swipe.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-surface-2 px-2 py-1 text-[11px] font-medium text-content-muted"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 text-sm text-content-muted">No swipes saved for this workspace yet.</div>
        )}
      </div>
    </div>
  );
}
