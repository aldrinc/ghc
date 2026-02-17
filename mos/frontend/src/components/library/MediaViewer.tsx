import { useEffect, useState, type ReactNode } from "react";
import type { MediaAsset } from "@/types/library";

function getThumb(asset: MediaAsset | undefined) {
  if (!asset) return "";
  if (asset.type === "video") return asset.posterUrl || asset.thumbUrl || "";
  return asset.thumbUrl || asset.url;
}

export function MediaTile({
  asset,
  count,
  className = "",
}: {
  asset?: MediaAsset;
  count?: number;
  className?: string;
}) {
  if (!asset) {
    return (
      <div
        className={`flex h-40 items-center justify-center rounded-lg border border-border bg-surface-2 text-sm text-content-muted ${className}`}
      >
        No media
      </div>
    );
  }

  if (asset.status === "failed") {
    return (
      <div
        className={`flex h-40 items-center justify-center rounded-lg border border-border bg-surface-2 text-sm text-content-muted ${className}`}
      >
        Media unavailable
      </div>
    );
  }

  const thumb = getThumb(asset);

  return (
    <div
      className={`relative overflow-hidden rounded-lg border border-border bg-surface-2 ${className}`}
    >
      {thumb ? (
        <img
          src={thumb}
          alt={asset.type === "image" ? asset.alt ?? "Media preview" : "Video preview"}
          className="h-40 w-full object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-40 items-center justify-center text-sm text-content-muted">
          {asset.type === "video" ? "Video" : "Image"}
        </div>
      )}

      {asset.status === "pending" && (
        <div className="absolute left-2 top-2 rounded-md bg-black/60 px-2 py-1 text-xs font-semibold text-white">
          Processing…
        </div>
      )}

      {asset.type === "video" && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/20">
          <div className="rounded-full bg-foreground/90 px-3 py-2 text-xs font-semibold text-background">
            ▶ Play
          </div>
        </div>
      )}

      {count && count > 1 && (
        <div className="absolute bottom-2 right-2 rounded-full bg-black/60 px-2 py-0.5 text-xs font-semibold text-white">
          {count}
        </div>
      )}
    </div>
  );
}

export function MediaViewer({
  assets,
  open,
  onClose,
  initialIndex = 0,
  title = "Preview",
  sidebar,
}: {
  assets: MediaAsset[];
  open: boolean;
  onClose: () => void;
  initialIndex?: number;
  title?: string;
  sidebar?: ReactNode;
}) {
  const [index, setIndex] = useState(initialIndex);

  useEffect(() => {
    if (open) setIndex(initialIndex);
  }, [open, initialIndex]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && assets.length > 1) {
        setIndex((i) => (i - 1 + assets.length) % assets.length);
      }
      if (e.key === "ArrowRight" && assets.length > 1) {
        setIndex((i) => (i + 1) % assets.length);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [assets.length, onClose, open]);

  if (!open) return null;

  const asset = assets[index];
  const src = asset?.fullUrl || asset?.url;
  const poster = asset?.posterUrl || asset?.thumbUrl;
  const hasSidebar = Boolean(sidebar);

  return (
    <div className="fixed inset-0 z-50">
      <button
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        aria-label="Close preview"
        type="button"
      />
      <div
        className={[
          "absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-surface p-4 text-content shadow-xl",
          hasSidebar ? "w-[min(96vw,1200px)]" : "w-[min(92vw,960px)]",
          "max-h-[92vh] overflow-hidden flex flex-col",
        ].join(" ")}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-semibold text-content">{title}</div>
          <button
            className="rounded-md px-2 py-1 text-sm text-content-muted hover:bg-hover hover:text-content"
            onClick={onClose}
            type="button"
          >
            ✕
          </button>
        </div>

        <div className="mt-3 min-h-0 flex-1 overflow-auto md:overflow-hidden">
          <div
            className={[
              hasSidebar ? "grid gap-3 md:grid-cols-[minmax(0,1fr),420px] md:items-start" : "",
            ].join(" ")}
          >
            <div className="min-w-0">
              <div className="relative overflow-hidden rounded-xl bg-black">
                {!asset ? (
                  <div className="flex h-[50vh] items-center justify-center text-white/70">No media</div>
                ) : asset.status === "failed" ? (
                  <div className="flex h-[50vh] items-center justify-center text-white/70">
                    Media unavailable
                  </div>
                ) : asset?.type === "video" && src ? (
                  <video
                    src={src}
                    poster={poster}
                    className="max-h-[72vh] w-full"
                    controls
                    autoPlay
                    playsInline
                  />
                ) : asset?.type === "image" && src ? (
                  <img
                    src={src}
                    alt={asset.alt ?? "Image"}
                    className="max-h-[72vh] w-full object-contain"
                  />
                ) : (
                  <div className="flex h-[50vh] items-center justify-center text-white/70">No media</div>
                )}
                {asset?.status === "pending" && (
                  <div className="absolute left-4 top-4 rounded-md bg-foreground/80 px-2 py-1 text-xs font-semibold text-background">
                    Processing…
                  </div>
                )}
              </div>

              {assets.length > 1 && (
                <div className="mt-3 flex items-center justify-between">
                  <button
                    className="rounded-md px-3 py-2 text-sm text-content hover:bg-hover"
                    onClick={() => setIndex((i) => (i - 1 + assets.length) % assets.length)}
                    type="button"
                  >
                    Prev
                  </button>
                  <div className="text-xs text-content-muted">
                    {index + 1} / {assets.length}
                  </div>
                  <button
                    className="rounded-md px-3 py-2 text-sm text-content hover:bg-hover"
                    onClick={() => setIndex((i) => (i + 1) % assets.length)}
                    type="button"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>

            {hasSidebar ? <div className="min-w-0">{sidebar}</div> : null}
          </div>
        </div>
      </div>
    </div>
  );
}
