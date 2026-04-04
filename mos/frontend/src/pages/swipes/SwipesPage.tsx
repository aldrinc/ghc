import { useCallback, useMemo, useState } from "react";
import { useCompanySwipes, useSwipeCollections, useSwipeReviewApi } from "@/api/swipes";
import { AssetReviewGrid } from "@/components/review/AssetReviewGrid";
import { SwipeDetailPanel } from "@/components/review/SwipeDetailPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Select } from "@/components/ui/select";
import { normalizeSwipeToAssetReviewItem } from "@/lib/assetReviewNormalizers";
import type { AssetReviewItem } from "@/types/assetReview";

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

export function SwipesPage() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [targetCollectionId, setTargetCollectionId] = useState("");
  const [detailItem, setDetailItem] = useState<AssetReviewItem | null>(null);

  const { data: swipes = [], isLoading, error } = useCompanySwipes({ source: "gethookd" });
  const { data: collections = [] } = useSwipeCollections();
  const { approveSwipes, rejectSwipes, markPendingSwipes } = useSwipeReviewApi();

  const launchableCollections = useMemo(
    () => collections.filter((c) => c.kind === "uploaded" || c.kind === "curated"),
    [collections],
  );

  const reviewItems = useMemo(
    () => swipes.map(normalizeSwipeToAssetReviewItem),
    [swipes],
  );

  const availablePlatforms = useMemo(() => {
    const set = new Set<string>();
    for (const item of reviewItems) {
      for (const p of item.platform) set.add(p);
    }
    return Array.from(set).sort();
  }, [reviewItems]);

  const stats = useMemo(
    () => ({
      total: swipes.length,
      pending: swipes.filter((s) => s.review_status === "pending_review").length,
      approved: swipes.filter((s) => s.review_status === "approved").length,
      rejected: swipes.filter((s) => s.review_status === "rejected").length,
      stale: swipes.filter((s) => s.review_status === "stale_after_sync").length,
    }),
    [swipes],
  );

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const handleCardClick = useCallback((item: AssetReviewItem) => {
    setDetailItem(item);
  }, []);

  const handleSingleApprove = useCallback(
    (id: string) => {
      if (!targetCollectionId) return;
      approveSwipes.mutate({ swipeAssetIds: [id], collectionId: targetCollectionId });
      setDetailItem(null);
    },
    [targetCollectionId, approveSwipes],
  );

  const handleSingleReject = useCallback(
    (id: string) => {
      rejectSwipes.mutate({ swipeAssetIds: [id] });
      setDetailItem(null);
    },
    [rejectSwipes],
  );

  const handleSingleMarkPending = useCallback(
    (id: string) => {
      markPendingSwipes.mutate({ swipeAssetIds: [id] });
      setDetailItem(null);
    },
    [markPendingSwipes],
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-content">GetHookd review inbox</h2>
          <p className="text-sm text-content-muted">
            Review nightly-synced reference ads, then promote approved items into launchable collections.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone="neutral">{stats.total} total</Badge>
          <Badge tone="warning">{stats.pending} pending</Badge>
          <Badge tone="success">{stats.approved} approved</Badge>
          <Badge tone="danger">{stats.rejected} rejected</Badge>
          <Badge tone="warning">{stats.stale} stale</Badge>
        </div>
      </div>

      {/* Bulk action bar */}
      {selectedIds.size > 0 ? (
        <div className="rounded-2xl border border-accent/30 bg-accent/5 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="text-sm text-content">
              <span className="font-semibold">{selectedIds.size}</span> selected
            </div>
            <div className="min-w-[240px] flex-1">
              <Select
                value={targetCollectionId}
                onValueChange={setTargetCollectionId}
                options={[
                  { label: "Add approved swipes to collection", value: "", disabled: true },
                  ...launchableCollections.map((c) => ({ label: c.name, value: c.id })),
                ]}
              />
            </div>
            <Button
              size="sm"
              onClick={() => {
                if (!targetCollectionId) return;
                approveSwipes.mutate({
                  swipeAssetIds: Array.from(selectedIds),
                  collectionId: targetCollectionId,
                });
                clearSelection();
              }}
              disabled={!targetCollectionId || approveSwipes.isPending}
            >
              Add to collection
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                rejectSwipes.mutate({ swipeAssetIds: Array.from(selectedIds) });
                clearSelection();
              }}
            >
              Reject
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                markPendingSwipes.mutate({ swipeAssetIds: Array.from(selectedIds) });
                clearSelection();
              }}
            >
              Mark pending
            </Button>
            <Button size="sm" variant="ghost" onClick={clearSelection}>
              Clear
            </Button>
          </div>
        </div>
      ) : null}

      {/* Errors */}
      {error ? (
        <Callout variant="danger" size="sm" title="Failed to load swipes">
          {getErrorMessage(error)}
        </Callout>
      ) : null}
      {approveSwipes.error ? (
        <Callout variant="danger" size="sm" title="Approve failed">
          {getErrorMessage(approveSwipes.error)}
        </Callout>
      ) : null}

      {/* Grid */}
      {isLoading ? (
        <div className="rounded-2xl border border-border bg-surface px-5 py-8 text-sm text-content-muted">
          Loading swipes…
        </div>
      ) : (
        <AssetReviewGrid
          items={reviewItems}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onCardClick={handleCardClick}
          availablePlatforms={availablePlatforms}
          emptyMessage="No GetHookd swipes match the current filters."
        />
      )}

      {/* Detail panel */}
      <SwipeDetailPanel
        item={detailItem}
        open={detailItem !== null}
        onClose={() => setDetailItem(null)}
        onApprove={targetCollectionId ? handleSingleApprove : undefined}
        onReject={handleSingleReject}
        onMarkPending={handleSingleMarkPending}
      />
    </div>
  );
}
