import { useCallback, useMemo, useState } from "react";
import { useGetHookdInbox, useSwipeCollections, useSwipeReviewApi } from "@/api/swipes";
import { AssetReviewGrid } from "@/components/review/AssetReviewGrid";
import { SwipeDetailPanel } from "@/components/review/SwipeDetailPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Select } from "@/components/ui/select";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
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
  const { workspace } = useWorkspace();
  const reviewLimit = 10;
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [targetCollectionId, setTargetCollectionId] = useState("");
  const [detailItem, setDetailItem] = useState<AssetReviewItem | null>(null);

  const { data: inbox, isLoading, error } = useGetHookdInbox(
    workspace?.id,
    reviewLimit,
    Boolean(workspace),
  );
  const { data: collections = [] } = useSwipeCollections();
  const { approveSwipes, rejectSwipes, markPendingSwipes } = useSwipeReviewApi();
  const swipes = inbox?.swipes ?? [];
  const summary = inbox?.summary ?? {
    latestRunId: null,
    latestRunStartedAt: null,
    rawImportedCount: 0,
    eligibleStaticImageCount: 0,
    duplicateCollapsedCount: 0,
    excludedNonStaticCount: 0,
    reviewLimit,
    returnedCount: 0,
    defaultAssetType: "image" as const,
  };

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
      total: summary.rawImportedCount,
      reviewable: summary.eligibleStaticImageCount,
      duplicates: summary.duplicateCollapsedCount,
      excluded: summary.excludedNonStaticCount,
      returned: summary.returnedCount,
      pending: swipes.filter((s) => s.review_status === "pending_review").length,
      approved: swipes.filter((s) => s.review_status === "approved").length,
      rejected: swipes.filter((s) => s.review_status === "rejected").length,
      stale: swipes.filter((s) => s.review_status === "stale_after_sync").length,
    }),
    [summary, swipes],
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

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="GetHookd review inbox"
          description="Select a workspace to review GetHookd swipes for that workspace."
        />
        <Callout variant="neutral" size="sm" title="Workspace required">
          Choose a workspace from the sidebar before opening GetHookd Collections.
        </Callout>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="GetHookd review inbox"
        description={`Review nightly-synced reference ads for ${workspace.name}, then promote approved items into launchable collections.`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Badge tone="neutral">{stats.total} raw imported</Badge>
            <Badge tone="success">{stats.reviewable} exact statics</Badge>
            <Badge tone="neutral">{stats.duplicates} duplicates collapsed</Badge>
            <Badge tone="neutral">{stats.excluded} excluded non-static</Badge>
            <Badge tone="neutral">{stats.returned} in review set</Badge>
            <Badge tone="warning">{stats.pending} pending</Badge>
            <Badge tone="success">{stats.approved} approved</Badge>
            <Badge tone="danger">{stats.rejected} rejected</Badge>
            <Badge tone="warning">{stats.stale} stale</Badge>
          </div>
        }
      />

      {summary.latestRunId ? (
        <Callout variant="neutral" size="sm" title="Latest GetHookd run">
          Showing the top {summary.returnedCount} exact static images from the latest workspace sync.
          Imported {summary.rawImportedCount} raw ads, kept {summary.eligibleStaticImageCount} exact
          statics, collapsed {summary.duplicateCollapsedCount} duplicates, excluded{" "}
          {summary.excludedNonStaticCount} non-static ads.
        </Callout>
      ) : (
        <Callout variant="neutral" size="sm" title="No GetHookd sync yet">
          Run a GetHookd sync for this workspace before opening the review inbox.
        </Callout>
      )}

      {selectedIds.size > 0 ? (
        <div className="ds-card ds-card--sm border-accent/25 bg-info-bg">
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
        <div className="ds-empty-surface text-sm text-content-muted">
          Loading swipes…
        </div>
      ) : (
        <AssetReviewGrid
          items={reviewItems}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onCardClick={handleCardClick}
          availablePlatforms={availablePlatforms}
          initialFilters={{ assetType: "image" }}
          emptyMessage="No exact static images are available in the latest GetHookd run."
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
