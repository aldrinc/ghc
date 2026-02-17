import { useEffect, useMemo, useState } from "react";
import { useApiClient } from "@/api/client";
import { LibraryCard } from "@/components/library/LibraryCard";
import { Callout } from "@/components/ui/callout";
import { normalizeSwipeToLibraryItem } from "@/lib/library";
import type { CompanySwipeAsset } from "@/types/swipes";

function LoadingGrid() {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-3 sm:gap-4">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div
          key={idx}
          className="ds-card ds-card--md flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-none animate-pulse"
        >
          <div className="relative">
            <div className="aspect-[4/5] w-full bg-muted" />
          </div>
          <div className="space-y-2 px-3 pb-3 pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="h-4 w-24 rounded-full bg-muted" />
              <div className="h-4 w-12 rounded-full bg-muted" />
              <div className="h-4 w-16 rounded-full bg-muted" />
            </div>
            <div className="h-3 w-3/4 rounded bg-muted" />
            <div className="h-3 w-5/6 rounded bg-muted" />
            <div className="h-3 w-1/2 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SwipesPage() {
  const { request } = useApiClient();
  const [swipes, setSwipes] = useState<CompanySwipeAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    request<CompanySwipeAsset[]>("/swipes/company")
      .then((data) => {
        if (cancelled) return;
        setSwipes(data);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setSwipes([]);
        setError(err?.message || "Failed to load swipes");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request]);

  const items = useMemo(() => swipes.map(normalizeSwipeToLibraryItem), [swipes]);

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-xl font-semibold text-content">Saved swipes</h2>
          <p className="text-sm text-content-muted">Manually curated references saved by your team.</p>
        </div>
      </div>
      {error ? (
        <Callout variant="danger" size="sm" title="Failed to load swipes">
          {error}
        </Callout>
      ) : null}
      {loading && <LoadingGrid />}
      {!loading && items.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-3 sm:gap-4">
          {items.map((item) => (
            <LibraryCard key={item.id} item={item} />
          ))}
        </div>
      )}
      {!loading && items.length === 0 && !error && (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          No swipes loaded. Save swipes from ad cards to see them here.
        </div>
      )}
    </div>
  );
}
