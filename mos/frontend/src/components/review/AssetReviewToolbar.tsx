import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AssetReviewFilterState } from "@/types/assetReview";

const REVIEW_STATUS_OPTIONS = [
  { label: "All review states", value: "all" },
  { label: "Pending review", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Stale after sync", value: "stale_after_sync" },
] as const;

const SOURCE_OPTIONS = [
  { label: "All sources", value: "all" },
  { label: "GetHookd", value: "gethookd" },
  { label: "Uploads", value: "upload" },
  { label: "Catalog", value: "catalog" },
  { label: "Unknown", value: "unknown" },
] as const;

const LAUNCH_OPTIONS = [
  { label: "All collection states", value: "all" },
  { label: "In launch collection", value: "in_launch" },
  { label: "Outside launch collection", value: "outside_launch" },
] as const;

const CHANGE_OPTIONS = [
  { label: "All freshness", value: "all" },
  { label: "Changed since last sync", value: "last_sync" },
  { label: "Changed in last 7 days", value: "last_7_days" },
] as const;

const ASSET_TYPE_OPTIONS = [
  { label: "All asset types", value: "all" },
  { label: "Static images", value: "image" },
  { label: "Videos", value: "video" },
  { label: "Carousels", value: "carousel" },
  { label: "Unknown", value: "unknown" },
] as const;

const DEFAULT_FILTER_STATE: AssetReviewFilterState = {
  search: "",
  reviewStatus: "all",
  source: "all",
  inLaunchCollection: null,
  changedSince: "all",
  platform: "all",
  assetType: "all",
};

function summarizeCounts(totalCount: number, filteredCount: number) {
  return filteredCount === totalCount
    ? `${totalCount} assets`
    : `${filteredCount} of ${totalCount} assets`;
}

export function AssetReviewToolbar({
  filters,
  onChange,
  availablePlatforms,
  totalCount,
  filteredCount,
  selectedCount,
}: {
  filters: AssetReviewFilterState;
  onChange: (next: AssetReviewFilterState) => void;
  availablePlatforms: string[];
  totalCount: number;
  filteredCount: number;
  selectedCount: number;
}) {
  const update = (partial: Partial<AssetReviewFilterState>) => onChange({ ...filters, ...partial });

  const resetFilters = () => onChange(DEFAULT_FILTER_STATE);

  return (
    <div className="rounded-2xl border border-border bg-surface px-3 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex flex-1 flex-wrap items-center gap-2.5">
          <input
            type="text"
            placeholder="Search brand, headline, body, or asset id…"
            className={cn(
              "h-9 min-w-[220px] rounded-md border border-border bg-surface px-3 text-xs text-content",
              "placeholder:text-content-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30",
            )}
            value={filters.search}
            onChange={(event) => update({ search: event.target.value })}
          />

          <select
            className="h-9 rounded-md border border-border bg-surface px-2.5 text-xs text-content"
            value={filters.reviewStatus}
            onChange={(event) =>
              update({ reviewStatus: event.target.value as AssetReviewFilterState["reviewStatus"] })
            }
          >
            {REVIEW_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <select
            className="h-9 rounded-md border border-border bg-surface px-2.5 text-xs text-content"
            value={filters.source}
            onChange={(event) => update({ source: event.target.value as AssetReviewFilterState["source"] })}
          >
            {SOURCE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <select
            className="h-9 rounded-md border border-border bg-surface px-2.5 text-xs text-content"
            value={
              filters.inLaunchCollection === null
                ? "all"
                : filters.inLaunchCollection
                  ? "in_launch"
                  : "outside_launch"
            }
            onChange={(event) =>
              update({
                inLaunchCollection:
                  event.target.value === "all"
                    ? null
                    : event.target.value === "in_launch",
              })
            }
          >
            {LAUNCH_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <select
            className="h-9 rounded-md border border-border bg-surface px-2.5 text-xs text-content"
            value={filters.changedSince}
            onChange={(event) =>
              update({ changedSince: event.target.value as AssetReviewFilterState["changedSince"] })
            }
          >
            {CHANGE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <select
            className="h-9 rounded-md border border-border bg-surface px-2.5 text-xs text-content"
            value={filters.assetType}
            onChange={(event) =>
              update({ assetType: event.target.value as AssetReviewFilterState["assetType"] })
            }
          >
            {ASSET_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          {availablePlatforms.length ? (
            <select
              className="h-9 rounded-md border border-border bg-surface px-2.5 text-xs text-content"
              value={filters.platform}
              onChange={(event) => update({ platform: event.target.value })}
            >
              <option value="all">All platforms</option>
              {availablePlatforms.map((platform) => (
                <option key={platform} value={platform}>
                  {platform}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <div className="text-right text-xs text-content-muted">
            <div>{summarizeCounts(totalCount, filteredCount)}</div>
            <div>{selectedCount} selected</div>
          </div>
          <Button variant="ghost" size="xs" onClick={resetFilters}>
            Clear
          </Button>
        </div>
      </div>
    </div>
  );
}
