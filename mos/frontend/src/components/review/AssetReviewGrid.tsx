import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  assetType: "all",
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
      ? new Date(now.getTime() - 24 * 60 * 60 * 1000)
      : new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    result = result.filter((item) => {
      const syncedAt = item.sourceLastSyncedAt ? new Date(item.sourceLastSyncedAt) : null;
      return syncedAt && syncedAt >= cutoff;
    });
  }

  if (filters.platform !== "all") {
    result = result.filter((item) => item.platform.includes(filters.platform));
  }

  if (filters.assetType !== "all") {
    result = result.filter((item) => (item.assetType ?? "unknown") === filters.assetType);
  }

  return result;
}

/**
 * Picks a grid column class based on the dominant orientation of the items.
 * Capped at 4 columns max so cards remain readable.
 */
function gridColumnsClass(items: AssetReviewItem[]): string {
  if (!items.length) return "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";

  let portrait = 0;
  for (const item of items) {
    const firstMedia = item.media[0];
    if (firstMedia?.type === "video" || firstMedia?.thumbUrl?.includes("portrait")) {
      portrait++;
    }
  }
  const portraitRatio = portrait / items.length;

  if (portraitRatio > 0.6) {
    return "grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4";
  }
  if (portraitRatio < 0.3) {
    return "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3";
  }
  return "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";
}

// ---------------------------------------------------------------------------
// Drag-select helpers
// ---------------------------------------------------------------------------

function getCardIdFromElement(el: Element | null): string | null {
  const card = el?.closest("[data-card-id]") as HTMLElement | null;
  return card?.dataset.cardId ?? null;
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
  initialFilters?: Partial<AssetReviewFilterState>;
}

/**
 * Shared asset review grid component.
 * Supports filtering, multi-select with drag-select mode, and detail panel opening.
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
  initialFilters,
}: AssetReviewGridProps) {
  const [filters, setFilters] = useState<AssetReviewFilterState>({
    ...DEFAULT_FILTER_STATE,
    ...initialFilters,
  });
  const [dragSelectMode, setDragSelectMode] = useState(false);

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

  // Track the last-clicked card id for shift+click range selection
  const lastClickedId = useRef<string | null>(null);

  const toggleSelect = useCallback(
    (id: string, shiftKey = false) => {
      const next = new Set(selectedIds);

      if (shiftKey && lastClickedId.current) {
        // Shift+click: select range between last-clicked and current
        const ids = filteredItems.map((item) => item.id);
        const from = ids.indexOf(lastClickedId.current);
        const to = ids.indexOf(id);
        if (from !== -1 && to !== -1) {
          const [start, end] = from < to ? [from, to] : [to, from];
          for (let i = start; i <= end; i++) {
            next.add(ids[i]);
          }
          onSelectionChange(next);
          lastClickedId.current = id;
          return;
        }
      }

      // Normal toggle
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      lastClickedId.current = id;
      onSelectionChange(next);
    },
    [selectedIds, filteredItems, onSelectionChange],
  );

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

  // ---------------------------------------------------------------------------
  // Drag-select state
  // ---------------------------------------------------------------------------
  const gridRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const dragBaseSelection = useRef<Set<string>>(new Set());
  const dragTouched = useRef<Set<string>>(new Set());

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (!dragSelectMode) return;
      // Only primary button
      if (e.button !== 0) return;
      // Don't hijack checkbox clicks
      if ((e.target as HTMLElement).closest("label, input")) return;

      isDragging.current = true;
      dragBaseSelection.current = new Set(selectedIds);
      dragTouched.current = new Set();

      const id = getCardIdFromElement(e.target as Element);
      if (id) {
        dragTouched.current.add(id);
        const next = new Set(dragBaseSelection.current);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        onSelectionChange(next);
      }

      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
      e.preventDefault();
    },
    [dragSelectMode, selectedIds, onSelectionChange],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging.current) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const id = getCardIdFromElement(el);
      if (!id || dragTouched.current.has(id)) return;

      dragTouched.current.add(id);
      const next = new Set(selectedIds);
      // Always add during drag (select mode)
      next.add(id);
      onSelectionChange(next);
    },
    [selectedIds, onSelectionChange],
  );

  const handlePointerUp = useCallback(() => {
    isDragging.current = false;
    dragTouched.current = new Set();
  }, []);

  // Escape key exits drag-select mode
  useEffect(() => {
    if (!dragSelectMode) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setDragSelectMode(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dragSelectMode]);

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
        <div className="flex items-center gap-4">
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

          <button
            type="button"
            className={cn(
              "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
              dragSelectMode
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-content-muted hover:border-border-strong hover:text-content",
            )}
            onClick={() => setDragSelectMode((v) => !v)}
            title="Toggle drag-to-select mode (Esc to exit)"
          >
            {dragSelectMode ? "Drag select on" : "Drag select"}
          </button>
        </div>

        {selectedIds.size > 0 && (
          <span className="text-xs text-content-muted">
            {selectedVisibleCount === selectedIds.size
              ? `${selectedIds.size} selected`
              : `${selectedVisibleCount} in view \u00B7 ${selectedIds.size} total selected`}
          </span>
        )}
      </div>

      {filteredItems.length ? (
        <div
          ref={gridRef}
          className={cn(
            `grid gap-4 ${colsClass}`,
            dragSelectMode && "cursor-crosshair select-none",
          )}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        >
          {filteredItems.map((item) => (
            <div key={item.id} data-card-id={item.id}>
              <AssetReviewCard
                item={item}
                selected={selectedIds.has(item.id)}
                onSelect={toggleSelect}
                onClick={dragSelectMode ? () => toggleSelect(item.id) : onCardClick}
              />
            </div>
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
