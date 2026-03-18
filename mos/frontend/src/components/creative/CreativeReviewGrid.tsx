import { useMemo, useState } from "react";
import type { AdReviewItem } from "@/types/creativeReview";
import { AdReviewCard, getCardOrientation } from "./AdReviewCard";
import {
  CreativeFilterBar,
  DEFAULT_FILTER_STATE,
  type CreativeFilterState,
} from "./CreativeFilterBar";

function matchesSearch(item: AdReviewItem, query: string): boolean {
  const q = query.toLowerCase();
  return (
    (item.headline?.toLowerCase().includes(q) ?? false) ||
    (item.primaryText?.toLowerCase().includes(q) ?? false) ||
    (item.description?.toLowerCase().includes(q) ?? false) ||
    (item.angle?.toLowerCase().includes(q) ?? false) ||
    (item.experimentName?.toLowerCase().includes(q) ?? false) ||
    (item.variantName?.toLowerCase().includes(q) ?? false) ||
    item.assetId.toLowerCase().includes(q)
  );
}

function applyFilters(
  items: AdReviewItem[],
  filters: CreativeFilterState,
  violationFilterEnabled: boolean,
): AdReviewItem[] {
  let result = items;

  if (filters.search) {
    result = result.filter((item) => matchesSearch(item, filters.search));
  }

  if (filters.specStatus === "ready") {
    result = result.filter((item) => item.specReady);
  } else if (filters.specStatus === "missing") {
    result = result.filter((item) => !item.specReady);
  }

  if (violationFilterEnabled) {
    if (filters.violationFilter === "has_violations") {
      result = result.filter((item) => item.violations.total > 0);
    } else if (filters.violationFilter === "clean") {
      result = result.filter((item) => item.violations.total === 0);
    }
  }

  if (filters.angleFilter !== "all") {
    result = result.filter((item) => item.angle === filters.angleFilter);
  }

  return result;
}

/**
 * Picks a grid column class based on the dominant orientation of the items.
 * Portrait-heavy batches get more columns since cards are narrower.
 */
function gridColumnsClass(items: AdReviewItem[]): string {
  if (!items.length) return "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5";

  let portrait = 0;
  for (const item of items) {
    if (getCardOrientation(item) === "portrait") portrait++;
  }
  const portraitRatio = portrait / items.length;

  if (portraitRatio > 0.6) {
    // Mostly portrait/story — use narrower, more columns
    return "grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6";
  }
  if (portraitRatio < 0.3) {
    // Mostly landscape/square — fewer wider columns
    return "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";
  }
  // Mixed — balanced default
  return "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5";
}

/**
 * The main creative review grid. Shows ad review cards with filtering,
 * multi-select, and triggers the detail panel on click.
 */
export function CreativeReviewGrid({
  items,
  selectedIds,
  onSelectionChange,
  onCardClick,
  violationFilterEnabled = true,
}: {
  items: AdReviewItem[];
  selectedIds: Set<string>;
  onSelectionChange: (next: Set<string>) => void;
  onCardClick: (item: AdReviewItem) => void;
  violationFilterEnabled?: boolean;
}) {
  const [filters, setFilters] = useState<CreativeFilterState>(DEFAULT_FILTER_STATE);

  const angles = useMemo(() => {
    const seen = new Set<string>();
    for (const item of items) {
      if (item.angle) seen.add(item.angle);
    }
    return Array.from(seen).sort();
  }, [items]);

  const filteredItems = useMemo(
    () => applyFilters(items, filters, violationFilterEnabled),
    [items, filters, violationFilterEnabled],
  );

  const colsClass = useMemo(() => gridColumnsClass(filteredItems), [filteredItems]);

  const toggleSelect = (assetId: string) => {
    const next = new Set(selectedIds);
    if (next.has(assetId)) {
      next.delete(assetId);
    } else {
      next.add(assetId);
    }
    onSelectionChange(next);
  };

  const toggleAll = () => {
    if (selectedIds.size === filteredItems.length) {
      onSelectionChange(new Set());
    } else {
      onSelectionChange(new Set(filteredItems.map((item) => item.assetId)));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-4">
        <CreativeFilterBar
          filters={filters}
          onChange={setFilters}
          angles={angles}
          totalCount={items.length}
          filteredCount={filteredItems.length}
          violationFilterEnabled={violationFilterEnabled}
        />
        <label className="flex shrink-0 items-center gap-2 text-xs text-content-muted">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border border-border bg-surface text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
            checked={filteredItems.length > 0 && selectedIds.size === filteredItems.length}
            onChange={toggleAll}
          />
          Select all ({filteredItems.length})
        </label>
      </div>

      {filteredItems.length ? (
        <div className={`grid gap-3 ${colsClass}`}>
          {filteredItems.map((item) => (
            <AdReviewCard
              key={item.assetId}
              item={item}
              selected={selectedIds.has(item.assetId)}
              onSelect={toggleSelect}
              onClick={onCardClick}
            />
          ))}
        </div>
      ) : (
        <div className="border border-border bg-transparent px-4 py-8 text-center text-sm text-content-muted">
          No ads match the current filters.
        </div>
      )}
    </div>
  );
}
