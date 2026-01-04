import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { LibraryCard } from "@/components/library/LibraryCard";
import { useExploreApi } from "@/api/explore";
import { normalizeExploreAdToLibraryItem } from "@/lib/library";
import type { LibraryItem } from "@/types/library";

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
  const { listAds } = useExploreApi();
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [limitPerBrand, setLimitPerBrand] = useState<number | undefined>(3);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listAds({
      q: query || undefined,
      channels: channel ? [channel] : undefined,
      status: status ? [status] : undefined,
      limitPerBrand: limitPerBrand || undefined,
      limit: 60,
      sort: "last_seen",
    })
      .then((resp) => {
        if (cancelled) return;
        const normalized = (resp?.items ?? []).map(normalizeExploreAdToLibraryItem);
        setItems(normalized);
        setCount(resp?.count ?? normalized.length);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setItems([]);
        setCount(0);
        setError(err?.message || "Failed to load ads");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [channel, listAds, limitPerBrand, query, status]);

  const filtersActive = useMemo(
    () => Boolean(channel || status || (limitPerBrand && limitPerBrand > 0) || query),
    [channel, limitPerBrand, query, status],
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Explore Ads"
        description="Browse ingested ads with basic filters and per-brand capping."
      />

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search copy, domains, brands"
          className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        />
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
              setLimitPerBrand(3);
            }}
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
          >
            Reset
          </button>
        ) : null}
      </div>

      <div className="flex items-center justify-between text-xs text-slate-600">
        <span>
          Showing {items.length} of {count || items.length} ads
        </span>
        <span className="text-slate-500">Phase 1 filters: channel, status, per-brand cap, search</span>
      </div>

      {error && <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{error}</div>}
      {loading && <LoadingGrid />}
      {!loading && items.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3 sm:gap-4">
          {items.map((item) => (
            <LibraryCard key={item.id} item={item} />
          ))}
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
