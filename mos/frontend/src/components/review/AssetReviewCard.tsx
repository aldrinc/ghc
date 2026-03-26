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

/**
 * All review cards use a consistent 4/5 aspect so rows align evenly.
 * The underlying media is object-cover'd, so nothing gets distorted.
 */
const CARD_ASPECT = "4/5" as const;

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
  onSelect: (id: string, shiftKey?: boolean) => void;
  onClick: (item: AssetReviewItem) => void;
}) {
  const lastSyncedLabel = compactDateLabel(item.sourceLastSyncedAt);
  const lastSeenLabel = compactDateLabel(item.sourceLastSeenAt);
  const performance = scoreLabel(item.performanceScore);

  return (
    <div
      className={cn(
        "group relative flex h-full flex-col overflow-hidden rounded-xl border bg-surface text-left transition-colors",
        selected
          ? "border-accent ring-1 ring-accent/20"
          : "border-border hover:border-border-strong",
      )}
    >
      <div className="relative border-b border-border bg-surface-2">
        <label className="absolute left-2 top-2 z-10">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border border-border bg-surface text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
            checked={selected}
            onChange={(e) => onSelect(item.id, e.nativeEvent instanceof MouseEvent ? e.nativeEvent.shiftKey : false)}
            aria-label={`Select ${item.brandName}`}
          />
        </label>

        <div className="pointer-events-none absolute right-2 top-2 z-10 flex flex-wrap justify-end gap-1">
          <Badge tone={reviewTone(item.reviewStatus)}>{reviewLabel(item.reviewStatus)}</Badge>
          <Badge tone={sourceTone(item.source)}>{sourceLabel(item.source)}</Badge>
        </div>

        <SwipeMedia media={item.media} aspect={CARD_ASPECT} onOpen={() => onClick(item)} />
      </div>

      <div
        className="flex flex-1 cursor-pointer flex-col gap-2 p-3"
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
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold leading-snug text-content">{item.headline || item.brandName}</div>
          </div>

          {performance ? (
            <div className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-right">
              <div className="text-[11px] uppercase tracking-wider text-content-muted">Score</div>
              <div className="text-sm font-semibold leading-none text-content">{performance}</div>
            </div>
          ) : null}
        </div>

        {item.body ? (
          <p className="line-clamp-2 text-xs leading-relaxed text-content-muted">{item.body}</p>
        ) : null}

        <div className="mt-auto space-y-2 pt-1">
          <div className="flex flex-wrap gap-1">
            {item.ctaText ? <Badge>{item.ctaText}</Badge> : null}
            {item.platform.map((platform) => (
              <Badge key={`${item.id}-${platform}`}>{channelDisplayName(platform)}</Badge>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] leading-relaxed text-content-muted">
            {item.destinationUrl ? (
              <a
                href={item.destinationUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-content-muted underline decoration-border underline-offset-2 hover:text-content hover:decoration-content-muted"
                title={item.destinationUrl}
                onClick={(e) => e.stopPropagation()}
              >
                {item.destinationHostname || item.destinationUrl}
              </a>
            ) : null}
            {typeof item.daysActive === "number" ? (
              <div className="truncate">{item.daysActive}d active</div>
            ) : null}
            {lastSyncedLabel ? (
              <div className="truncate">Synced {lastSyncedLabel}</div>
            ) : null}
            {lastSeenLabel ? (
              <div className="truncate">Seen {lastSeenLabel}</div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
