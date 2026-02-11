import { Play } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { MediaAsset } from "@/types/library";

const VIDEO_HOVER_PREVIEW_DELAY_MS = 1000;

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

function mediaThumb(asset?: MediaAsset) {
  if (!asset) return "";
  if (asset.type === "video") {
    return asset.posterUrl || asset.thumbUrl || asset.url;
  }
  return asset.thumbUrl || asset.url;
}

function MediaContent({ asset }: { asset?: MediaAsset }) {
  const [errored, setErrored] = useState(false);

  const thumb = mediaThumb(asset);

  useEffect(() => {
    setErrored(false);
  }, [thumb]);

  if (!asset) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-content-muted">
        No media
      </div>
    );
  }

  if (asset.status === "pending") {
    return (
      <div className="flex h-full animate-pulse items-center justify-center text-sm text-content-muted">
        Processing media…
      </div>
    );
  }

  if (asset.status === "failed") {
    return (
      <div className="flex h-full items-center justify-center text-sm text-content-muted">
        Media unavailable
      </div>
    );
  }

  if (!thumb) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-content-muted">
        No media
      </div>
    );
  }

  if (errored) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-content-muted">
        Media unavailable
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
        onError={() => setErrored(true)}
      />
    </>
  );
}

function VideoHoverPreview({
  asset,
  aspectClass,
  onClick,
}: {
  asset: Extract<MediaAsset, { type: "video" }>;
  aspectClass: string;
  onClick?: () => void;
}) {
  const [errored, setErrored] = useState(false);
  const [previewActive, setPreviewActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hoverDelayTimerRef = useRef<number | null>(null);

  const sourceUrl = asset.fullUrl || asset.url;
  const posterUrl = asset.posterUrl || asset.thumbUrl;

  const clearHoverDelay = useCallback(() => {
    if (hoverDelayTimerRef.current !== null) {
      window.clearTimeout(hoverDelayTimerRef.current);
      hoverDelayTimerRef.current = null;
    }
  }, []);

  const stopPreview = useCallback(() => {
    clearHoverDelay();
    setPreviewActive(false);
  }, [clearHoverDelay]);

  useEffect(() => {
    setErrored(false);
    stopPreview();
  }, [asset.fullUrl, asset.posterUrl, asset.status, asset.thumbUrl, asset.url, stopPreview]);

  useEffect(() => {
    return () => {
      clearHoverDelay();
    };
  }, [clearHoverDelay]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (!previewActive) {
      video.pause();
      video.currentTime = 0;
      return;
    }

    video.currentTime = 0;
    const playPromise = video.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {
        setPreviewActive(false);
      });
    }
  }, [previewActive]);

  const handlePointerEnter = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== "mouse") return;
    if (asset.status === "pending" || asset.status === "failed" || errored || !sourceUrl) return;
    clearHoverDelay();
    hoverDelayTimerRef.current = window.setTimeout(() => {
      setPreviewActive(true);
      hoverDelayTimerRef.current = null;
    }, VIDEO_HOVER_PREVIEW_DELAY_MS);
  };

  return (
    <div
      className={`group relative overflow-hidden rounded-xl border border-border bg-surface-2 ${aspectClass}`}
      onClick={onClick}
      onPointerEnter={handlePointerEnter}
      onPointerLeave={stopPreview}
      role="presentation"
    >
      {asset.status === "pending" ? (
        <div className="flex h-full animate-pulse items-center justify-center text-sm text-content-muted">
          Processing media…
        </div>
      ) : asset.status === "failed" || errored ? (
        <div className="flex h-full items-center justify-center text-sm text-content-muted">
          Media unavailable
        </div>
      ) : previewActive && sourceUrl ? (
        <video
          ref={videoRef}
          src={sourceUrl}
          poster={posterUrl}
          className="h-full w-full object-cover"
          muted
          playsInline
          loop
          preload="metadata"
          onError={() => {
            setErrored(true);
            setPreviewActive(false);
          }}
        />
      ) : posterUrl ? (
        <img
          src={posterUrl}
          alt="Video preview"
          className="h-full w-full object-cover"
          loading="lazy"
          draggable={false}
          onError={() => setErrored(true)}
        />
      ) : (
        <div className="flex h-full items-center justify-center text-sm text-content-muted">Video</div>
      )}

      {!previewActive && asset.status !== "pending" && asset.status !== "failed" && !errored ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-black/55 text-white shadow-md backdrop-blur-sm">
            <Play className="h-5 w-5 fill-white" />
          </div>
        </div>
      ) : null}
    </div>
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
      <div className={`relative overflow-hidden rounded-xl border border-border bg-surface-2 ${aspectClass}`}>
        <MediaContent />
      </div>
    );
  }

  const go = (delta: number) => {
    setIndex((i) => (i + delta + media.length) % media.length);
  };

  return (
    <div
      className={`group relative overflow-hidden rounded-xl border border-border bg-surface-2 ${aspectClass}`}
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
  const primaryVideoAsset = assets.find((asset) => asset.type === "video");

  if (assets.length === 0) {
    return (
      <div className={`flex items-center justify-center rounded-xl border border-border bg-surface-2 text-sm text-content-muted ${aspectClass}`}>
        No media
      </div>
    );
  }

  if (primaryVideoAsset) {
    return <VideoHoverPreview asset={primaryVideoAsset} aspectClass={aspectClass} onClick={onOpen} />;
  }

  if (assets.length === 1) {
    return (
      <div
        className={`relative overflow-hidden rounded-xl border border-border bg-surface-2 ${aspectClass}`}
        onClick={onOpen}
        role="presentation"
      >
        <MediaContent asset={assets[0]} />
      </div>
    );
  }

  return <SwipeCarousel media={assets} aspectClass={aspectClass} onClick={onOpen} />;
}
