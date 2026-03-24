import { useEffect, useMemo, useState } from "react";
import { useSwipeCollection, useSwipeCollections } from "@/api/swipes";
import { LibraryCard } from "@/components/library/LibraryCard";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { normalizeSwipeToLibraryItem } from "@/lib/library";
import { cn } from "@/lib/utils";
import type { SwipeCollection } from "@/types/swipes";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

function resolvePreferredCollectionId(collections: SwipeCollection[]) {
  return collections.find((collection) => collection.kind === "default")?.id || collections[0]?.id || "";
}

function CollectionListSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, idx) => (
        <div
          key={idx}
          className="rounded-xl border border-border bg-surface px-4 py-3 animate-pulse"
        >
          <div className="h-4 w-2/3 rounded bg-muted" />
          <div className="mt-3 flex gap-2">
            <div className="h-5 w-16 rounded-full bg-muted" />
            <div className="h-5 w-20 rounded-full bg-muted" />
          </div>
          <div className="mt-3 h-3 w-1/2 rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}

function SwipeGridSkeleton() {
  return (
    <div className="flex flex-wrap gap-3 sm:gap-4">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div
          key={idx}
          className="w-full max-w-[360px] flex-none overflow-hidden rounded-2xl border border-border bg-surface animate-pulse"
        >
          <div className="aspect-[4/5] w-full bg-muted" />
          <div className="space-y-2 px-3 pb-3 pt-3">
            <div className="h-4 w-24 rounded-full bg-muted" />
            <div className="h-3 w-3/4 rounded bg-muted" />
            <div className="h-3 w-5/6 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

function CollectionCard({
  collection,
  selected,
  onClick,
}: {
  collection: SwipeCollection;
  selected: boolean;
  onClick: () => void;
}) {
  const readyCount = collection.analysis_counts.ready || 0;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-xl border px-4 py-3 text-left transition",
        selected
          ? "border-accent bg-accent/5 shadow-sm"
          : "border-border bg-surface hover:border-accent/40 hover:bg-surface-2",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-content">{collection.name}</div>
          <div className="mt-1 text-xs text-content-muted">
            Created {formatDate(collection.created_at)}
          </div>
        </div>
        {selected ? <Badge tone="accent">Selected</Badge> : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone="neutral">{collection.kind}</Badge>
        <Badge tone="neutral">{collection.item_count} swipes</Badge>
        <Badge tone={readyCount > 0 ? "success" : "neutral"}>{readyCount} ready</Badge>
        <Badge tone={collection.writable ? "success" : "warning"}>
          {collection.writable ? "Writable" : "Read-only"}
        </Badge>
      </div>
    </button>
  );
}

export function SwipesPage() {
  const {
    data: collections = [],
    isLoading: collectionsLoading,
    error: collectionsError,
  } = useSwipeCollections();
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);

  useEffect(() => {
    if (collectionsLoading) return;
    if (!collections.length) {
      setSelectedCollectionId(null);
      return;
    }
    if (selectedCollectionId && collections.some((collection) => collection.id === selectedCollectionId)) {
      return;
    }
    setSelectedCollectionId(resolvePreferredCollectionId(collections));
  }, [collections, collectionsLoading, selectedCollectionId]);

  const selectedCollection = useMemo(
    () => collections.find((collection) => collection.id === selectedCollectionId) ?? null,
    [collections, selectedCollectionId],
  );
  const {
    data: selectedCollectionDetail,
    isLoading: collectionDetailLoading,
    error: collectionDetailError,
  } = useSwipeCollection(selectedCollectionId);

  const items = useMemo(
    () => (selectedCollectionDetail?.swipes || []).map(normalizeSwipeToLibraryItem),
    [selectedCollectionDetail?.swipes],
  );
  const totalSavedSwipes = useMemo(
    () => collections.reduce((sum, collection) => sum + collection.item_count, 0),
    [collections],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-content">Swipe collections</h2>
          <p className="text-sm text-content-muted">
            Browse every saved collection and inspect the exact swipes inside each set.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone="neutral">{collections.length} collections</Badge>
          <Badge tone="neutral">{totalSavedSwipes} saved swipes</Badge>
        </div>
      </div>

      {collectionsError ? (
        <Callout variant="danger" size="sm" title="Failed to load swipe collections">
          {getErrorMessage(collectionsError)}
        </Callout>
      ) : null}

      {collectionDetailError ? (
        <Callout variant="danger" size="sm" title="Failed to load selected collection">
          {getErrorMessage(collectionDetailError)}
        </Callout>
      ) : null}

      {!collectionsLoading && collections.length === 0 ? (
        <div className="rounded-2xl border border-border bg-surface px-5 py-8 text-sm text-content-muted">
          No swipe collections exist yet. Create one from a campaign generation screen to start curating saved swipes.
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">
              All collections
            </div>
            {collectionsLoading ? (
              <CollectionListSkeleton />
            ) : (
              collections.map((collection) => (
                <CollectionCard
                  key={collection.id}
                  collection={collection}
                  selected={collection.id === selectedCollectionId}
                  onClick={() => setSelectedCollectionId(collection.id)}
                />
              ))
            )}
          </div>

          <div className="space-y-4">
            {selectedCollection ? (
              <div className="rounded-2xl border border-border bg-surface p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold text-content">{selectedCollection.name}</div>
                    <div className="mt-1 text-sm text-content-muted">
                      {selectedCollection.kind} collection · created {formatDate(selectedCollection.created_at)}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge tone="neutral">{selectedCollection.id.slice(0, 8)}</Badge>
                    <Badge tone="neutral">{selectedCollection.item_count} swipes</Badge>
                    <Badge tone={(selectedCollection.analysis_counts.ready || 0) > 0 ? "success" : "neutral"}>
                      {selectedCollection.analysis_counts.ready || 0} ready
                    </Badge>
                    <Badge tone={selectedCollection.writable ? "success" : "warning"}>
                      {selectedCollection.writable ? "Writable" : "Read-only"}
                    </Badge>
                  </div>
                </div>
              </div>
            ) : null}

            {collectionDetailLoading ? (
              <SwipeGridSkeleton />
            ) : items.length > 0 ? (
              <div className="flex flex-wrap gap-3 sm:gap-4">
                {items.map((item) => (
                  <div key={item.id} className="w-full max-w-[360px] flex-none">
                    <LibraryCard item={item} />
                  </div>
                ))}
              </div>
            ) : selectedCollection ? (
              <div className="rounded-2xl border border-border bg-surface px-5 py-8 text-sm text-content-muted">
                This collection does not contain any swipes yet.
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
