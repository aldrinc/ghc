import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { LibraryCard } from "@/components/library/LibraryCard";
import { useExploreApi } from "@/api/explore";
import { normalizeExploreAdToLibraryItem } from "@/lib/library";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { LibraryItem } from "@/types/library";

const PAGE_SIZE = 60;

const channelOptions = [
  { value: "", label: "All channels" },
  { value: "META_ADS_LIBRARY", label: "Meta" },
  { value: "TIKTOK_CREATIVE_CENTER", label: "TikTok" },
  { value: "GOOGLE_ADS_TRANSPARENCY", label: "Google" },
];

const statusOptions = [
  { value: "", label: "Any status" },
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "unknown", label: "Unknown" },
];

function LoadingGrid() {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3 sm:gap-4">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div
          key={idx}
          className="ds-card ds-card--md flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-none animate-pulse"
        >
          <div className="relative">
            <div className="aspect-[4/5] w-full bg-muted" />
            <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="h-5 w-20 rounded-full bg-black/20" />
                <div className="h-5 w-12 rounded-full bg-black/20" />
              </div>
              <div className="h-4 w-24 rounded-full bg-black/20" />
            </div>
          </div>
          <div className="space-y-2 px-3 pb-3 pt-3">
            <div className="h-3 w-3/4 rounded bg-muted" />
            <div className="h-3 w-5/6 rounded bg-muted" />
            <div className="h-3 w-1/2 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ExploreAdsPage() {
  const { listAds, listBrands } = useExploreApi();
  const { workspace } = useWorkspace();
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [brandId, setBrandId] = useState("");
  const [brandOptions, setBrandOptions] = useState<{ value: string; label: string }[]>([]);
  const [brandsLoading, setBrandsLoading] = useState(false);
  const [brandError, setBrandError] = useState<string | null>(null);
  const [limitPerBrand, setLimitPerBrand] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [scope, setScope] = useState<"workspace" | "global">(workspace ? "workspace" : "global");
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const filtersKeyRef = useRef<string>("");

  useEffect(() => {
    if (!workspace && scope === "workspace") {
      setScope("global");
    }
  }, [scope, workspace]);

  const errorMessage = useCallback((err: any, fallback: string) => {
    const msg = err?.message;
    return typeof msg === "string" ? msg : fallback;
  }, []);

  const scopedClientId = scope === "workspace" ? workspace?.id : undefined;

  const baseParams = useMemo(
    () => ({
      q: query || undefined,
      channels: channel ? [channel] : undefined,
      status: status ? [status] : undefined,
      brandIds: brandId ? [brandId] : undefined,
      clientId: scopedClientId,
      limitPerBrand: limitPerBrand || undefined,
      sort: "last_seen",
    }),
    [brandId, channel, limitPerBrand, query, scopedClientId, status],
  );

  const filtersKey = useMemo(
    () =>
      JSON.stringify({
        ...baseParams,
        scope,
      }),
    [baseParams, scope],
  );

  useEffect(() => {
    filtersKeyRef.current = filtersKey;
  }, [filtersKey]);

  useEffect(() => {
    let cancelled = false;
    setBrandsLoading(true);
    listBrands({
      clientId: scopedClientId,
      includeHidden: false,
      sort: "name",
      direction: "asc",
      limit: 200,
    })
      .then((resp) => {
        if (cancelled) return;
        const options =
          (resp?.items ?? []).map((brand) => {
            const name =
              brand.brand_name || brand.primary_domain || brand.primary_website_url || "Unknown brand";
            const domain = brand.primary_domain || brand.primary_website_url;
            const label = domain && domain !== name ? `${name} (${domain})` : name;
            return { value: brand.brand_id, label };
          }) || [];
        setBrandOptions(options);
        setBrandError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setBrandOptions([]);
        setBrandError(errorMessage(err, "Failed to load competitors"));
      })
      .finally(() => {
        if (!cancelled) {
          setBrandsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [listBrands, scopedClientId]);

  useEffect(() => {
    let cancelled = false;
    filtersKeyRef.current = filtersKey;
    setItems([]);
    setCount(0);
    setHasMore(false);
    setNextOffset(0);
    setLoading(true);
    setError(null);
    setLoadingMore(false);
    listAds({
      ...baseParams,
      limit: PAGE_SIZE,
      offset: 0,
    })
      .then((resp) => {
        if (cancelled || filtersKeyRef.current !== filtersKey) return;
        const normalized = (resp?.items ?? []).map(normalizeExploreAdToLibraryItem);
        setError(null);
        const totalCount = resp?.count ?? normalized.length;
        setItems(normalized);
        setCount(totalCount);
        setHasMore(normalized.length < totalCount);
        setNextOffset(normalized.length);
      })
      .catch((err) => {
        if (cancelled || filtersKeyRef.current !== filtersKey) return;
        setItems([]);
        setCount(0);
        setHasMore(false);
        setError(errorMessage(err, "Failed to load ads"));
      })
      .finally(() => {
        if (cancelled || filtersKeyRef.current !== filtersKey) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [baseParams, filtersKey, listAds]);

  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore) return;
    const currentKey = filtersKeyRef.current;
    setLoadingMore(true);
    listAds({
      ...baseParams,
      limit: PAGE_SIZE,
      offset: nextOffset,
    })
      .then((resp) => {
        if (filtersKeyRef.current !== currentKey) return;
        const normalized = (resp?.items ?? []).map(normalizeExploreAdToLibraryItem);
        const totalCount = resp?.count ?? count;
        setItems((prev) => {
          const nextItems = [...prev, ...normalized];
          const resolvedCount = totalCount ?? nextItems.length;
          setCount(resolvedCount);
          setHasMore(normalized.length > 0 && nextItems.length < resolvedCount);
          setNextOffset(nextItems.length);
          return nextItems;
        });
        setError(null);
      })
      .catch((err) => {
        if (filtersKeyRef.current !== currentKey) return;
        setError(errorMessage(err, "Failed to load ads"));
      })
      .finally(() => {
        if (filtersKeyRef.current !== currentKey) return;
        setLoadingMore(false);
      });
  }, [baseParams, count, hasMore, listAds, loading, loadingMore, nextOffset]);

  useEffect(() => {
    const node = loadMoreRef.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          loadMore();
        }
      },
      { rootMargin: "240px 0px 240px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  const filtersActive = useMemo(
    () => Boolean(channel || status || brandId || (limitPerBrand && limitPerBrand > 0) || query),
    [brandId, channel, limitPerBrand, query, status],
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Explore Ads"
        description="Browse ingested ads with basic filters and per-brand capping."
      />

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value as "workspace" | "global")}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          <option value="workspace" disabled={!workspace}>
            Workspace only{workspace?.name ? ` (${workspace.name})` : ""}
          </option>
          <option value="global">All org ads (global)</option>
        </select>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search copy, domains, brands"
          className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        />
        <select
          value={brandId}
          onChange={(e) => setBrandId(e.target.value)}
          disabled={brandsLoading && !brandOptions.length}
          aria-label="Filter by competitor"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          <option value="">{brandsLoading ? "Loading competitors..." : "All competitors"}</option>
          {brandOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          {channelOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          {statusOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-2">
          <label className="text-xs font-semibold text-slate-600">Limit per brand</label>
          <input
            type="number"
            min={1}
            value={limitPerBrand ?? ""}
            onChange={(e) => {
              const value = e.target.value;
              setLimitPerBrand(value ? Math.max(1, Number(value)) : undefined);
            }}
            className="w-20 rounded-lg border border-slate-200 px-2 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
          />
        </div>
        {filtersActive ? (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setChannel("");
              setStatus("");
              setBrandId("");
              setLimitPerBrand(undefined);
            }}
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
          >
            Reset
          </button>
        ) : null}
      </div>
      {brandError && (
        <div className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">{brandError}</div>
      )}

      <div className="flex flex-col gap-1 text-xs text-slate-600 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Showing {items.length} of {count || items.length} ads
        </span>
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
          <span className="text-slate-500">
            Scope: {scope === "workspace" ? workspace?.name || "Workspace" : "Global"}
          </span>
          <span className="text-slate-500">Phase 1 filters: competitor, channel, status, per-brand cap, search</span>
        </div>
      </div>

      {error && <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{error}</div>}
      {loading && <LoadingGrid />}
      {!loading && items.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3 sm:gap-4">
          {items.map((item) => (
            <LibraryCard key={item.id} item={item} />
          ))}
          {(hasMore || loadingMore) && (
            <div ref={loadMoreRef} className="col-span-full flex items-center justify-center py-4">
              {loadingMore ? (
                <span className="text-sm text-slate-500">Loading more ads…</span>
              ) : (
                <span className="text-sm text-slate-400">Keep scrolling to load more</span>
              )}
            </div>
          )}
        </div>
      )}
      {!loading && items.length === 0 && !error && (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          No ads match these filters yet.
        </div>
      )}
    </div>
  );
}
