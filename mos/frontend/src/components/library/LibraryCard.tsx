import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { MediaViewer } from "@/components/library/MediaViewer";
import { LibraryItemDetailsPanel } from "@/components/library/LibraryItemDetailsPanel";
import { SwipeMedia } from "@/components/library/SwipeMedia";
import { Badge } from "@/components/ui/badge";
import { channelDisplayName } from "@/lib/channels";
import type { LibraryItem } from "@/types/library";

type LibraryCardProps = {
  item: LibraryItem;
  saved?: boolean;
  onSave?: (item: LibraryItem) => void | Promise<void>;
  onOpenSource?: (item: LibraryItem) => void;
  onCopyLink?: (item: LibraryItem) => void;
};

function HorizontalBadgeScroller({ ariaLabel, children }: { ariaLabel: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [isScrollable, setIsScrollable] = useState(false);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const overflow = el.scrollWidth > el.clientWidth + 1;
    if (!overflow) {
      setIsScrollable(false);
      setCanScrollLeft(false);
      setCanScrollRight(false);
      return;
    }

    setIsScrollable(true);
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    update();
    const el = ref.current;
    if (!el) return;

    const onScroll = () => update();
    el.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", update);

    return () => {
      el.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", update);
    };
  }, [update]);

  const scrollBy = (delta: number) => {
    const el = ref.current;
    if (!el) return;
    el.scrollBy({ left: delta, behavior: "smooth" });
  };

  return (
    <div className="relative">
      <div
        ref={ref}
        aria-label={ariaLabel}
        className={[
          "flex items-center gap-1.5 overflow-x-auto overflow-y-hidden whitespace-nowrap [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
          isScrollable ? "px-6" : "",
        ].join(" ")}
      >
        {children}
      </div>

      {isScrollable ? (
        <>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-surface to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-surface to-transparent" />
          <button
            type="button"
            aria-label="Scroll badges left"
            disabled={!canScrollLeft}
            onClick={(e) => {
              e.stopPropagation();
              scrollBy(-160);
            }}
            className="absolute left-0 top-1/2 z-10 inline-flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-surface/90 text-content shadow-sm transition hover:bg-hover disabled:opacity-30"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Scroll badges right"
            disabled={!canScrollRight}
            onClick={(e) => {
              e.stopPropagation();
              scrollBy(160);
            }}
            className="absolute right-0 top-1/2 z-10 inline-flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-surface/90 text-content shadow-sm transition hover:bg-hover disabled:opacity-30"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </>
      ) : null}
    </div>
  );
}

export function LibraryCard({ item, saved, onSave, onOpenSource, onCopyLink }: LibraryCardProps) {
  const [open, setOpen] = useState(false);
  const primary = item.media[0];
  const score = item.scores;

  const starLabel = useMemo(() => {
    const stars = score?.performanceStars;
    if (!stars || stars < 1) return null;
    const filled = "★".repeat(Math.min(stars, 5));
    const empty = "☆".repeat(Math.max(0, 5 - stars));
    return `${filled}${empty}`;
  }, [score?.performanceStars]);

  const statusLabel = useMemo(() => {
    if (!item.status) return null;
    return item.status === "active" ? "Active" : item.status === "inactive" ? "Inactive" : "Unknown";
  }, [item.status]);

  const hasActions = onSave || onOpenSource || onCopyLink;
  const hasVideo = useMemo(() => item.media.some((asset) => asset.type === "video"), [item.media]);
  const formatLabel = useMemo(() => {
    if (hasVideo) return "Video";
    if (item.media.length > 1) return "Carousel";
    if (primary?.type === "image") return "Image";
    return null;
  }, [hasVideo, item.media.length, primary?.type]);

  const handleCardActivate = () => {
    if (item.media.length === 0) return;
    setOpen(true);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleCardActivate();
    }
  };

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        onClick={handleCardActivate}
        onKeyDown={handleKeyDown}
        className="flex h-full w-full flex-col overflow-hidden rounded-2xl border border-border bg-surface text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        <div className="relative">
          <SwipeMedia media={item.media} aspect="4/5" onOpen={handleCardActivate} />
        </div>

        {hasActions ? (
          <div className="flex flex-wrap items-center gap-2 px-3 pt-3">
            {onSave ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onSave?.(item);
                }}
                className={[
                  "rounded-full border px-3 py-1 text-xs font-medium transition",
                  saved
                    ? "border-success/30 bg-success/10 text-success"
                    : "border-border bg-muted text-content hover:bg-hover",
                ].join(" ")}
              >
                {saved ? "Saved" : "Save"}
              </button>
            ) : null}
            {onOpenSource ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenSource?.(item);
                }}
                className="rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-content transition hover:bg-hover"
              >
                Open source
              </button>
            ) : null}
            {onCopyLink ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onCopyLink?.(item);
                }}
                className="rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-content transition hover:bg-hover"
              >
                Copy link
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="flex min-h-40 flex-1 flex-col gap-1 px-3 pb-4 pt-4">
          <HorizontalBadgeScroller ariaLabel="Brand and CTA badges">
            <Badge className="shrink-0 whitespace-nowrap text-[11px] uppercase tracking-wide">{item.brandName}</Badge>
            {score?.winningScore ? (
              <Badge tone="success" className="shrink-0 whitespace-nowrap text-[11px] uppercase tracking-wide">
                {score.winningScore}
              </Badge>
            ) : null}
            {item.ctaText ? (
              <Badge tone="success" className="shrink-0 whitespace-nowrap text-[11px] uppercase tracking-wide">
                {item.ctaText}
              </Badge>
            ) : null}
          </HorizontalBadgeScroller>
          {item.headline && (
            <div className="line-clamp-2 text-sm font-semibold text-content">{item.headline}</div>
          )}
          {item.body && <p className="line-clamp-3 text-sm text-content-muted">{item.body}</p>}
          <div className="mt-auto text-xs text-content-muted">
            <HorizontalBadgeScroller ariaLabel="Ad metadata badges">
              {formatLabel ? (
                <Badge className="shrink-0 whitespace-nowrap text-[11px]">{formatLabel}</Badge>
              ) : null}
              {item.platform?.map((platform) => (
                <Badge key={`${item.id}-${platform}`} className="shrink-0 whitespace-nowrap text-[11px]">
                  {channelDisplayName(platform)}
                </Badge>
              ))}
              {starLabel ? (
                <Badge className="shrink-0 whitespace-nowrap text-[11px] font-mono">{starLabel}</Badge>
              ) : null}
              {statusLabel ? (
                <Badge className="shrink-0 whitespace-nowrap text-[11px]">{statusLabel}</Badge>
              ) : null}
            </HorizontalBadgeScroller>
          </div>
        </div>
      </div>

      <MediaViewer
        assets={item.media}
        open={open}
        onClose={() => setOpen(false)}
        title={item.brandName}
        sidebar={<LibraryItemDetailsPanel item={item} />}
      />
    </>
  );
}
