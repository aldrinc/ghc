import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AdReviewItem } from "@/types/creativeReview";
import { ViolationBanner } from "./ViolationBanner";

function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/**
 * Derives a display aspect-ratio class from the asset's dimensions or format string.
 * Returns a Tailwind aspect-ratio utility so the image container sizes correctly.
 */
function getAspectClass(item: AdReviewItem): string {
  // If we have real dimensions, compute the ratio bucket
  if (item.width && item.height) {
    const ratio = item.width / item.height;
    if (ratio < 0.7) return "aspect-[9/16]"; // story / portrait
    if (ratio <= 0.85) return "aspect-[4/5]"; // 4:5
    if (ratio <= 1.15) return "aspect-square"; // square-ish
    return "aspect-video"; // landscape
  }
  // Fall back to format string
  const fmt = item.format.toLowerCase();
  if (fmt.includes("story") || fmt.includes("9:16") || fmt.includes("9_16")) return "aspect-[9/16]";
  if (fmt.includes("portrait") || fmt.includes("4:5") || fmt.includes("4_5")) return "aspect-[4/5]";
  if (fmt.includes("square") || fmt.includes("1:1") || fmt.includes("1_1")) return "aspect-square";
  if (fmt.includes("landscape") || fmt.includes("16:9") || fmt.includes("feed")) return "aspect-video";
  return "aspect-square"; // safe default
}

/**
 * Returns "portrait" | "landscape" | "square" bucket for grid layout decisions.
 */
export function getCardOrientation(item: AdReviewItem): "portrait" | "landscape" | "square" {
  if (item.width && item.height) {
    const ratio = item.width / item.height;
    if (ratio < 0.85) return "portrait";
    if (ratio > 1.15) return "landscape";
    return "square";
  }
  const fmt = item.format.toLowerCase();
  if (fmt.includes("story") || fmt.includes("portrait") || fmt.includes("9:16") || fmt.includes("4:5")) return "portrait";
  if (fmt.includes("landscape") || fmt.includes("16:9") || fmt.includes("feed")) return "landscape";
  return "square";
}

/**
 * A single card in the creative review grid.
 * Renders with format-aware aspect ratios for efficient space use.
 */
export function AdReviewCard({
  item,
  selected,
  onSelect,
  onClick,
}: {
  item: AdReviewItem;
  selected: boolean;
  onSelect: (assetId: string) => void;
  onClick: (item: AdReviewItem) => void;
}) {
  const isExcluded = item.publishDecision === "excluded";
  const aspectClass = getAspectClass(item);

  return (
    <div
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-lg border bg-surface transition",
        selected
          ? "border-accent ring-2 ring-accent/20"
          : "border-border hover:border-accent/50",
        isExcluded && "opacity-50",
      )}
    >
      {/* Checkbox overlay */}
      <label className="absolute left-2 top-2 z-10">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border border-border bg-surface text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
          checked={selected}
          onChange={() => onSelect(item.assetId)}
        />
      </label>

      {/* Image / Preview area — aspect ratio driven by format */}
      <button
        type="button"
        className="relative w-full cursor-pointer border-b border-border bg-surface-2"
        onClick={() => onClick(item)}
      >
        {item.imageUrl ? (
          <img
            src={item.imageUrl}
            alt={item.imageAlt}
            className={cn("w-full object-cover", aspectClass)}
            loading="lazy"
          />
        ) : (
          <div className={cn("flex w-full items-center justify-center text-sm text-content-muted", aspectClass)}>
            No preview
          </div>
        )}

        {/* Status overlays */}
        {isExcluded ? (
          <div className="absolute inset-0 flex items-center justify-center bg-surface/60">
            <Badge tone="neutral">Excluded</Badge>
          </div>
        ) : null}
      </button>

      {/* Card body — compact */}
      <div
        className="flex flex-1 cursor-pointer flex-col gap-1.5 p-2.5"
        onClick={() => onClick(item)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") onClick(item);
        }}
      >
        {/* Ad copy summary */}
        <div className="min-w-0">
          {item.headline ? (
            <div className="truncate text-xs font-semibold text-content">
              {item.headline}
            </div>
          ) : (
            <div className="text-xs text-content-muted italic">No headline</div>
          )}
          {item.primaryText ? (
            <div className="mt-0.5 text-[11px] leading-tight text-content-muted line-clamp-2">
              {truncate(item.primaryText, 120)}
            </div>
          ) : null}
        </div>

        {/* Context tags — tighter */}
        <div className="flex flex-wrap gap-0.5">
          {item.specReady ? (
            <Badge tone="success">Spec ready</Badge>
          ) : (
            <Badge tone="neutral">No spec</Badge>
          )}
          {item.copySource === "swipe_copy_pack" ? (
            <Badge tone="accent">Swipe copy</Badge>
          ) : null}
          {item.angle ? (
            <span className="inline-flex items-center rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] text-content-muted">
              {truncate(item.angle, 24)}
            </span>
          ) : null}
        </div>

        {/* Violations */}
        <ViolationBanner violations={item.violations} />
      </div>
    </div>
  );
}
