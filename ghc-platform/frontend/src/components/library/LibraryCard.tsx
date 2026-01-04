import { useMemo, useState, type KeyboardEvent } from "react";
import { MediaViewer } from "@/components/library/MediaViewer";
import { SwipeMedia } from "@/components/library/SwipeMedia";
import type { LibraryItem } from "@/types/library";

type LibraryCardProps = {
  item: LibraryItem;
  saved?: boolean;
  onSave?: (item: LibraryItem) => void | Promise<void>;
  onOpenSource?: (item: LibraryItem) => void;
  onCopyLink?: (item: LibraryItem) => void;
};

export function LibraryCard({ item, saved, onSave, onOpenSource, onCopyLink }: LibraryCardProps) {
  const [open, setOpen] = useState(false);
  const primary = item.media[0];
  const platformLabel = item.platform?.length ? item.platform.join(", ") : "Unknown platform";
  const score = item.scores;

  const starLabel = useMemo(() => {
    const stars = score?.performanceStars;
    if (!stars || stars < 1) return null;
    const filled = "★".repeat(Math.min(stars, 5));
    const empty = "☆".repeat(Math.max(0, 5 - stars));
    return `${filled}${empty}`;
  }, [score?.performanceStars]);

  const confidenceDisplay = useMemo(() => {
    if (typeof score?.confidence !== "number") return null;
    return Number(score.confidence).toFixed(2);
  }, [score?.confidence]);

  const statusLabel = useMemo(() => {
    if (!item.status) return null;
    return item.status === "active" ? "Active" : item.status === "inactive" ? "Inactive" : "Unknown";
  }, [item.status]);

  const hasActions = onSave || onOpenSource || onCopyLink;
  const formatLabel = useMemo(() => {
    if (item.media.length > 1) return "Carousel";
    if (primary?.type === "video") return "Video";
    if (primary?.type === "image") return "Image";
    return null;
  }, [item.media.length, primary?.type]);

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
        className="flex h-full w-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-300"
      >
        <div className="relative">
          <SwipeMedia media={item.media} aspect="4/5" onOpen={handleCardActivate} />
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-3 text-xs font-semibold text-white drop-shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <span className="truncate rounded-full bg-black/65 px-2.5 py-1 text-[11px] uppercase tracking-wide">
                {item.brandName}
              </span>
              {score?.winningScore ? (
                <span className="rounded-full bg-emerald-500/85 px-2.5 py-1 text-[11px] uppercase tracking-wide">
                  {score.winningScore}
                </span>
              ) : null}
              {item.ctaText ? (
                <span className="rounded-full bg-emerald-500/80 px-2.5 py-1 text-[11px] uppercase tracking-wide">
                  {item.ctaText}
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-1 text-[11px]">
              {formatLabel && <span className="rounded-full bg-black/55 px-2 py-0.5">{formatLabel}</span>}
              {item.platform?.length ? (
                <span className="rounded-full bg-black/45 px-2 py-0.5">{platformLabel}</span>
              ) : null}
              {starLabel ? <span className="rounded-full bg-black/45 px-2 py-0.5 font-mono">{starLabel}</span> : null}
            </div>
          </div>
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
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-slate-200 bg-slate-50 hover:bg-slate-100",
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
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium transition hover:bg-slate-100"
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
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium transition hover:bg-slate-100"
              >
                Copy link
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-1 flex-col gap-1 px-3 pb-3 pt-3">
          {item.headline && (
            <div className="line-clamp-2 text-sm font-semibold text-slate-900">{item.headline}</div>
          )}
          {item.body && <p className="line-clamp-3 text-sm text-slate-600">{item.body}</p>}
          <div className="mt-auto flex items-center justify-between text-xs text-slate-500">
            <span className="truncate">
              {platformLabel}
              {statusLabel ? ` • ${statusLabel}` : ""}
            </span>
            <span className="flex items-center gap-1 font-medium text-slate-700">
              {score?.performanceScore ? `P ${score.performanceScore}` : ""}
              {confidenceDisplay ? (
                <span className="text-[11px] text-slate-500">c{confidenceDisplay}</span>
              ) : null}
              {item.funnelStage || formatLabel || ""}
            </span>
          </div>
        </div>
      </div>

      <MediaViewer assets={item.media} open={open} onClose={() => setOpen(false)} title={item.brandName} />
    </>
  );
}
