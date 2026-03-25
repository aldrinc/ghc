import { useMemo, useState } from "react";
import type { AssetReviewItem, AssetReviewFilterState } from "@/types/assetReview";
import { AssetReviewCard } from "./AssetReviewCard";
import { AssetReviewToolbar } from "./AssetReviewToolbar";
import { cn } from "@/lib/utils";

const DEFAULT_FILTER_STATE: AssetReviewFilterState = {
  search: "",
  reviewStatus: "all",
  source: "all",
  inLaunchCollection: null,
  changedSince: "all",
  platform: "all",
};

function matchesSearch(item: AssetReviewItem, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return (
    (item.headline?.toLowerCase().includes(q) ?? false) ||
    (item.body?.toLowerCase().includes(q) ?? false) ||
    (item.brandName?.toLowerCase().includes(q) ?? false) ||
    item.id.toLowerCase().includes(q)
  );
}

function applyFilters(
  items: AssetReviewItem[],
  filters: AssetReviewFilterState,
): AssetReviewItem[] {
  let result = items;

  if (filters.search) {
    result = result.filter((item) => matchesSearch(item, filters.search));
  }

  if (filters.reviewStatus !== "all") {
    result = result.filter((item) => item.reviewStatus === filters.reviewStatus);
  }

  if (filters.source !== "all") {
    result = result.filter((item) => item.source === filters.source);
  }

  if (filters.inLaunchCollection !== null) {
    result = result.filter((item) => item.isInLaunchCollection === filters.inLaunchCollection);
  }

  if (filters.changedSince !== "all") {
    const now = new Date();
    const cutoff = filters.changedSince === "last_sync" 
      ? new Date(now.getTime() - 24 * 60 * 60 * 1000) // Last 24 hours
      : new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000); // Last 7 days
    
    result = result.filter((item) => {
      const syncedAt = item.sourceLastSyncedAt ? new Date(item.sourceLastSyncedAt) : null;
      return syncedAt && syncedAt >= cutoff;
    });
  }

  if (filters.platform !== "all") {
    result = result.filter((item) => item.platform.includes(filters.platform));
  }

  return result;
}

/**
 * Picks a grid column class based on the dominant orientation of the items.
 */
function gridColumnsClass(items: AssetReviewItem[]): string {
  if (!items.length) return "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5";

  let portrait = 0;
  for (const item of items) {
    const firstMedia = item.media[0];
    if (firstMedia?.type === "video" || firstMedia?.thumbUrl?.includes("portrait")) {
      portrait++;
    }
  }
  const portraitRatio = portrait / items.length;

  if (portraitRatio > 0.6) {
    return "grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6";
  }
  if (portraitRatio < 0.3) {
    return "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";
  }
  return "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5";
}

interface AssetReviewGridProps {
  items: AssetReviewItem[];
  selectedIds: Set<string>;
  onSelectionChange: (next: Set<string>) => void;
  onCardClick: (item: AssetReviewItem) => void;
  availablePlatforms?: string[];
  className?: string;
  showFilters?: boolean;
  emptyMessage?: string;
}

/**
 * Shared asset review grid component.
 * Supports filtering, multi-select, and detail panel opening.
 * Used for GetHookd review, swipe review, and creative review.
 */
export function AssetReviewGrid({
  items,
  selectedIds,
  onSelectionChange,
  onCardClick,
  availablePlatforms = [],
  className,
  showFilters = true,
  emptyMessage = "No assets match the current filters.",
}: AssetReviewGridProps) {
  const [filters, setFilters] = useState<AssetReviewFilterState>(DEFAULT_FILTER_STATE);

  const filteredItems = useMemo(
    () => applyFilters(items, filters),
    [items, filters]
  );

  const colsClass = useMemo(() => gridColumnsClass(filteredItems), [filteredItems]);
  const filteredIds = useMemo(() => new Set(filteredItems.map((item) => item.id)), [filteredItems]);
  const selectedVisibleCount = useMemo(
    () => Array.from(selectedIds).filter((id) => filteredIds.has(id)).length,
    [filteredIds, selectedIds]
  );

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onSelectionChange(next);
  };

  const toggleAll = () => {
    if (selectedVisibleCount === filteredItems.length && filteredItems.length > 0) {
      const next = new Set(selectedIds);
      for (const item of filteredItems) {
        next.delete(item.id);
      }
      onSelectionChange(next);
    } else {
      const next = new Set(selectedIds);
      for (const item of filteredItems) {
        next.add(item.id);
      }
      onSelectionChange(next);
    }
  };

  const allSelected = filteredItems.length > 0 && selectedVisibleCount === filteredItems.length;
  const someSelected = selectedVisibleCount > 0 && selectedVisibleCount < filteredItems.length;

  return (
    <div className={cn("space-y-3", className)}>
      {showFilters && (
        <AssetReviewToolbar
          filters={filters}
          onChange={setFilters}
          availablePlatforms={availablePlatforms}
          totalCount={items.length}
          filteredCount={filteredItems.length}
          selectedCount={selectedIds.size}
        />
      )}

      <div className="flex items-center justify-between gap-4">
        <label className="flex shrink-0 items-center gap-2 text-xs text-content-muted">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border border-border bg-surface text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
            checked={allSelected}
            ref={(input) => {
              if (input) {
                input.indeterminate = someSelected;
              }
            }}
            onChange={toggleAll}
          />
          Select all ({filteredItems.length})
        </label>
        
        {selectedIds.size > 0 && (
          <span className="text-xs text-content-muted">
            {selectedVisibleCount === selectedIds.size
              ? `${selectedIds.size} selected`
              : `${selectedVisibleCount} in view • ${selectedIds.size} total selected`}
          </span>
        )}
      </div>

      {filteredItems.length ? (
        <div className={`grid gap-3 ${colsClass}`}>
          {filteredItems.map((item) => (
            <AssetReviewCard
              key={item.id}
              item={item}
              selected={selectedIds.has(item.id)}
              onSelect={toggleSelect}
              onClick={onCardClick}
            />
          ))}
        </div>
      ) : (
        <div className="border border-border bg-transparent px-4 py-8 text-center text-sm text-content-muted">
          {emptyMessage}
        </div>
      )}
    </div>
  );
}
