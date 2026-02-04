import { useMemo, useState } from "react";
import type { MediaAsset } from "@/types/library";

function aspectToClass(aspect: "1/1" | "4/5" | "9/16" | "16/9") {
  switch (aspect) {
    case "1/1":
      return "aspect-square";
    case "9/16":
      return "aspect-[9/16]";
    case "16/9":
      return "aspect-video";
    case "4/5":
    default:
      return "aspect-[4/5]";
  }
}

function MediaContent({ asset }: { asset?: MediaAsset }) {
  if (!asset) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        No media
      </div>
    );
  }

  if (asset.status === "pending") {
    return (
      <div className="flex h-full animate-pulse items-center justify-center text-sm text-slate-500">
        Processing media…
      </div>
    );
  }

  if (asset.status === "failed") {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Media unavailable
      </div>
    );
  }

  const thumb =
    asset.type === "video"
      ? asset.posterUrl || asset.thumbUrl || asset.url
      : asset.thumbUrl || asset.url;

  if (!thumb) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        No media
      </div>
    );
  }

  return (
    <>
      <img
        src={thumb}
        alt={asset.type === "image" ? asset.alt ?? "Image preview" : "Video preview"}
        className="h-full w-full object-cover"
        loading="lazy"
        draggable={false}
      />
      {asset.type === "video" && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/10">
          <div className="rounded-full bg-black/70 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white">
            Play
          </div>
        </div>
      )}
    </>
  );
}

export function SwipeCarousel({
  media,
  aspectClass,
  onClick,
}: {
  media: MediaAsset[];
  aspectClass: string;
  onClick?: () => void;
}) {
  const [index, setIndex] = useState(0);
  const current = useMemo(() => media[index] || media[0], [index, media]);

  if (!media.length) {
    return (
      <div className={`relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50 ${aspectClass}`}>
        <MediaContent />
      </div>
    );
  }

  const go = (delta: number) => {
    setIndex((i) => (i + delta + media.length) % media.length);
  };

  return (
    <div
      className={`group relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50 ${aspectClass}`}
      onClick={onClick}
      role="presentation"
    >
      <MediaContent asset={current} />

      <button
        type="button"
        aria-label="Previous"
        onClick={(e) => {
          e.stopPropagation();
          go(-1);
        }}
        className="absolute left-2 top-1/2 inline-flex -translate-y-1/2 items-center justify-center rounded-full bg-black/60 p-2 text-white opacity-90 shadow-sm transition hover:bg-black/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        {"<"}
      </button>
      <button
        type="button"
        aria-label="Next"
        onClick={(e) => {
          e.stopPropagation();
          go(1);
        }}
        className="absolute right-2 top-1/2 inline-flex -translate-y-1/2 items-center justify-center rounded-full bg-black/60 p-2 text-white opacity-90 shadow-sm transition hover:bg-black/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        {">"}
      </button>

      <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1">
        {media.map((_, idx) => (
          <button
            key={idx}
            type="button"
            aria-label={`Go to media ${idx + 1}`}
            onClick={(e) => {
              e.stopPropagation();
              setIndex(idx);
            }}
            className={[
              "h-2 w-2 rounded-full transition",
              idx === index ? "bg-white" : "bg-white/60",
            ].join(" ")}
          />
        ))}
      </div>
    </div>
  );
}

export function SwipeMedia({
  media,
  aspect = "4/5",
  onOpen,
}: {
  media: MediaAsset[];
  aspect?: "1/1" | "4/5" | "9/16" | "16/9";
  onOpen?: () => void;
}) {
  const aspectClass = aspectToClass(aspect);
  const assets = media || [];

  if (assets.length === 0) {
    return (
      <div className={`flex items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-sm text-slate-500 ${aspectClass}`}>
        No media
      </div>
    );
  }

  if (assets.length === 1) {
    return (
      <div
        className={`relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50 ${aspectClass}`}
        onClick={onOpen}
        role="presentation"
      >
        <MediaContent asset={assets[0]} />
      </div>
    );
  }

  return <SwipeCarousel media={assets} aspectClass={aspectClass} onClick={onOpen} />;
}
