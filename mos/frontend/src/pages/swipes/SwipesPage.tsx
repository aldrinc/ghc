import { useMemo, useState } from "react";
import { useCompanySwipes, useSwipeCollections, useSwipeReviewApi } from "@/api/swipes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { normalizeSwipeToLibraryItem } from "@/lib/library";
import { cn } from "@/lib/utils";
import type { CompanySwipeAsset, SwipeReviewFilter } from "@/types/swipes";

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusTone(status?: string) {
  if (status === "approved") return "success" as const;
  if (status === "rejected") return "danger" as const;
  if (status === "stale_after_sync") return "warning" as const;
  return "neutral" as const;
}

function formatHostname(url?: string) {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function ReviewCard({
  swipe,
  selected,
  onToggle,
}: {
  swipe: CompanySwipeAsset;
  selected: boolean;
  onToggle: () => void;
}) {
  const item = useMemo(() => normalizeSwipeToLibraryItem(swipe), [swipe]);
  const preview = item.media[0]?.thumbUrl || item.media[0]?.url;
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "relative rounded-2xl border bg-surface p-3 text-left transition",
        selected ? "border-accent ring-1 ring-accent/30" : "border-border hover:border-accent/40",
      )}
    >
      <div className="absolute right-3 top-3">
        <input type="checkbox" readOnly checked={selected} className="h-4 w-4 rounded border-border" />
      </div>
      <div className="mb-3 aspect-[4/5] overflow-hidden rounded-xl border border-border bg-surface-2">
        {preview ? (
          <img src={preview} alt={swipe.title || "Swipe preview"} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-content-muted">No media</div>
        )}
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap gap-2">
          <Badge tone={statusTone(swipe.review_status)}>{swipe.review_status || "unknown"}</Badge>
          {swipe.analysis_status ? <Badge tone="neutral">{swipe.analysis_status}</Badge> : null}
          {swipe.performance_score ? <Badge tone="neutral">Score {swipe.performance_score}</Badge> : null}
          {swipe.days_active ? <Badge tone="neutral">{swipe.days_active}d active</Badge> : null}
        </div>
        <div className="text-sm font-semibold text-content line-clamp-2">{swipe.title || swipe.body || swipe.id}</div>
        {swipe.body ? <div className="line-clamp-3 text-xs text-content-muted">{swipe.body}</div> : null}
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-content-muted">
          {swipe.platforms ? <span>{swipe.platforms}</span> : null}
          {swipe.used_count ? <span>{swipe.used_count} used</span> : null}
          {swipe.landing_page ? <span>{formatHostname(swipe.landing_page)}</span> : null}
          <span>Synced {formatDate(swipe.source_last_synced_at)}</span>
        </div>
      </div>
    </button>
  );
}

export function SwipesPage() {
  const [filters, setFilters] = useState<SwipeReviewFilter>({
    source: "gethookd",
    reviewStatus: "pending",
    changedSince: "all",
  });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [targetCollectionId, setTargetCollectionId] = useState("");
  const { data: swipes = [], isLoading, error } = useCompanySwipes(filters);
  const { data: collections = [] } = useSwipeCollections();
  const { approveSwipes, rejectSwipes, markPendingSwipes } = useSwipeReviewApi();

  const launchableCollections = useMemo(
    () => collections.filter((collection) => collection.kind === "uploaded" || collection.kind === "curated"),
    [collections],
  );

  const stats = useMemo(
    () => ({
      total: swipes.length,
      pending: swipes.filter((swipe) => swipe.review_status === "pending_review").length,
      approved: swipes.filter((swipe) => swipe.review_status === "approved").length,
      rejected: swipes.filter((swipe) => swipe.review_status === "rejected").length,
      stale: swipes.filter((swipe) => swipe.review_status === "stale_after_sync").length,
    }),
    [swipes],
  );

  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const toggle = (swipeId: string) => {
    setSelectedIds((current) =>
      current.includes(swipeId) ? current.filter((id) => id !== swipeId) : [...current, swipeId],
    );
  };

  const clearSelection = () => setSelectedIds([]);

  return (
    <div className="space-y-4">
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

      <div className="rounded-2xl border border-border bg-surface p-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <div className="xl:col-span-2">
            <div className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Search</div>
            <Input
              value={filters.search || ""}
              onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
              placeholder="Search title, body, or external id"
            />
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Review status</div>
            <Select
              value={filters.reviewStatus || "all"}
              onValueChange={(value) =>
                setFilters((current) => ({ ...current, reviewStatus: value as SwipeReviewFilter["reviewStatus"] }))
              }
              options={[
                { label: "All", value: "all" },
                { label: "Pending", value: "pending" },
                { label: "Approved", value: "approved" },
                { label: "Rejected", value: "rejected" },
                { label: "Stale", value: "stale" },
              ]}
            />
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Changed since</div>
            <Select
              value={filters.changedSince || "all"}
              onValueChange={(value) =>
                setFilters((current) => ({ ...current, changedSince: value as SwipeReviewFilter["changedSince"] }))
              }
              options={[
                { label: "All", value: "all" },
                { label: "Last sync", value: "last_sync" },
                { label: "Last 7 days", value: "last_7_days" },
              ]}
            />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm text-content-muted">
              <input
                type="checkbox"
                checked={Boolean(filters.notInLaunchCollection)}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, notInLaunchCollection: event.target.checked }))
                }
              />
              Not in launch collection
            </label>
          </div>
        </div>
      </div>

      {selectedIds.length > 0 ? (
        <div className="rounded-2xl border border-accent/30 bg-accent/5 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="text-sm text-content">
              <span className="font-semibold">{selectedIds.length}</span> selected
            </div>
            <div className="min-w-[240px] flex-1">
              <Select
                value={targetCollectionId}
                onValueChange={setTargetCollectionId}
                options={[
                  { label: "Add approved swipes to collection", value: "", disabled: true },
                  ...launchableCollections.map((collection) => ({ label: collection.name, value: collection.id })),
                ]}
              />
            </div>
            <Button
              size="sm"
              onClick={() => {
                if (!targetCollectionId) return;
                approveSwipes.mutate({ swipeAssetIds: selectedIds, collectionId: targetCollectionId });
                clearSelection();
              }}
              disabled={!targetCollectionId || approveSwipes.isPending}
            >
              Add to collection
            </Button>
            <Button size="sm" variant="secondary" onClick={() => { rejectSwipes.mutate({ swipeAssetIds: selectedIds }); clearSelection(); }}>
              Reject
            </Button>
            <Button size="sm" variant="secondary" onClick={() => { markPendingSwipes.mutate({ swipeAssetIds: selectedIds }); clearSelection(); }}>
              Mark pending
            </Button>
            <Button size="sm" variant="ghost" onClick={clearSelection}>
              Clear
            </Button>
          </div>
        </div>
      ) : null}

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

      {isLoading ? (
        <div className="rounded-2xl border border-border bg-surface px-5 py-8 text-sm text-content-muted">Loading swipes…</div>
      ) : swipes.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {swipes.map((swipe) => (
            <ReviewCard
              key={swipe.id}
              swipe={swipe}
              selected={selectedIdSet.has(swipe.id)}
              onToggle={() => toggle(swipe.id)}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-border bg-surface px-5 py-8 text-sm text-content-muted">
          No GetHookd swipes match the current filters.
        </div>
      )}
    </div>
  );
}
