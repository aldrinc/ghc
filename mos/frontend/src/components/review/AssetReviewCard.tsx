import { Badge } from "@/components/ui/badge";
import { SwipeMedia } from "@/components/library/SwipeMedia";
import { channelDisplayName } from "@/lib/channels";
import { cn } from "@/lib/utils";
import type { AssetReviewItem, ReviewStatus } from "@/types/assetReview";

function reviewTone(status: ReviewStatus): "neutral" | "success" | "danger" | "warning" {
  switch (status) {
    case "approved":
      return "success";
    case "rejected":
      return "danger";
    case "stale_after_sync":
      return "warning";
    case "pending_review":
    default:
      return "neutral";
  }
}

function reviewLabel(status: ReviewStatus): string {
  switch (status) {
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "stale_after_sync":
      return "Stale";
    case "pending_review":
    default:
      return "Pending";
  }
}

function sourceLabel(source: AssetReviewItem["source"]): string {
  switch (source) {
    case "gethookd":
      return "GetHookd";
    case "upload":
      return "Upload";
    case "catalog":
      return "Catalog";
    case "unknown":
    default:
      return "Unknown";
  }
}

function sourceTone(source: AssetReviewItem["source"]): "accent" | "neutral" {
  return source === "gethookd" ? "accent" : "neutral";
}

function resolveAspect(item: AssetReviewItem): "1/1" | "4/5" | "9/16" | "16/9" {
  const firstMedia = item.media[0];
  if (!firstMedia) return "4/5";

  const descriptor = [firstMedia.url, firstMedia.thumbUrl, firstMedia.type].join(" ").toLowerCase();
  if (descriptor.includes("16x9") || descriptor.includes("16/9") || descriptor.includes("landscape")) {
    return "16/9";
  }
  if (descriptor.includes("square") || descriptor.includes("1x1") || descriptor.includes("1/1")) {
    return "1/1";
  }
  if (firstMedia.type === "video" || descriptor.includes("portrait") || descriptor.includes("9x16")) {
    return "9/16";
  }
  return "4/5";
}

function compactDateLabel(value?: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function scoreLabel(value?: number): string | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function AssetReviewCard({
  item,
  selected,
  onSelect,
  onClick,
}: {
  item: AssetReviewItem;
  selected: boolean;
  onSelect: (id: string) => void;
  onClick: (item: AssetReviewItem) => void;
}) {
  const aspect = resolveAspect(item);
  const lastSyncedLabel = compactDateLabel(item.sourceLastSyncedAt);
  const lastSeenLabel = compactDateLabel(item.sourceLastSeenAt);
  const performance = scoreLabel(item.performanceScore);

  return (
    <div
      className={cn(
        "group relative flex h-full flex-col overflow-hidden rounded-2xl border bg-surface text-left transition",
        selected
          ? "border-accent ring-2 ring-accent/20"
          : "border-border hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md",
      )}
    >
      <div className="relative border-b border-border bg-surface-2">
        <label className="absolute left-2 top-2 z-10">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border border-border bg-surface text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
            checked={selected}
            onChange={() => onSelect(item.id)}
            aria-label={`Select ${item.brandName}`}
          />
        </label>

        <div className="pointer-events-none absolute right-2 top-2 z-10 flex flex-wrap justify-end gap-1">
          <Badge tone={reviewTone(item.reviewStatus)}>{reviewLabel(item.reviewStatus)}</Badge>
          <Badge tone={sourceTone(item.source)}>{sourceLabel(item.source)}</Badge>
        </div>

        <SwipeMedia media={item.media} aspect={aspect} onOpen={() => onClick(item)} />
      </div>

      <div
        className="flex flex-1 cursor-pointer flex-col gap-3 px-3 pb-4 pt-3"
        onClick={() => onClick(item)}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onClick(item);
          }
        }}
      >
        <div className="space-y-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-content">{item.brandName}</div>
              {item.headline ? (
                <div className="mt-0.5 line-clamp-2 text-sm text-content">{item.headline}</div>
              ) : null}
            </div>

            {performance ? (
              <div className="shrink-0 text-right">
                <div className="text-[10px] uppercase tracking-[0.18em] text-content-muted">Score</div>
                <div className="text-sm font-semibold text-content">{performance}</div>
              </div>
            ) : null}
          </div>

          {item.body ? (
            <p className="line-clamp-3 text-xs leading-relaxed text-content-muted">{item.body}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-1.5">
          {item.isInLaunchCollection ? <Badge tone="success">Launch collection</Badge> : null}
          {item.status === "active" ? <Badge tone="success">Active</Badge> : null}
          {item.status === "inactive" ? <Badge tone="warning">Inactive</Badge> : null}
          {item.performanceTier ? <Badge>{item.performanceTier}</Badge> : null}
          {item.ctaText ? <Badge>{item.ctaText}</Badge> : null}
        </div>

        <div className="mt-auto space-y-2">
          {item.platform.length ? (
            <div className="flex flex-wrap gap-1.5">
              {item.platform.map((platform) => (
                <Badge key={`${item.id}-${platform}`}>{channelDisplayName(platform)}</Badge>
              ))}
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-content-muted">
            <div className="truncate">
              <span className="font-medium text-content">Hostname:</span>{" "}
              {item.destinationHostname || "Unknown"}
            </div>
            <div className="truncate">
              <span className="font-medium text-content">Days active:</span>{" "}
              {typeof item.daysActive === "number" ? item.daysActive : "Unknown"}
            </div>
            <div className="truncate">
              <span className="font-medium text-content">Last synced:</span> {lastSyncedLabel || "Unknown"}
            </div>
            <div className="truncate">
              <span className="font-medium text-content">Last seen:</span> {lastSeenLabel || "Unknown"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
