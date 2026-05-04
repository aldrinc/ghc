import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { cn } from "@/lib/utils";
import type { MediaAsset } from "@/types/library";

type SwipeMediaFit = "cover" | "contain";

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

function mediaFitClass(fit: SwipeMediaFit) {
  return fit === "contain" ? "h-full w-full object-contain" : "h-full w-full object-cover";
}

function MediaContent({
  asset,
  fit = "cover",
}: {
  asset?: MediaAsset;
  fit?: SwipeMediaFit;
}) {
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
        className={mediaFitClass(fit)}
        loading="lazy"
        draggable={false}
        onError={() => setErrored(true)}
      />
    </>
  );
}

/**
 * Video card with explicit play/pause controls.
 * The media surface itself is reserved for playback so card-level open actions
 * are not triggered when the user interacts with the video.
 */
function VideoHoverPreview({
  asset,
  aspectClass,
  fit = "cover",
  onClick,
}: {
  asset: Extract<MediaAsset, { type: "video" }>;
  aspectClass: string;
  fit?: SwipeMediaFit;
  onClick?: () => void;
}) {
  const [errored, setErrored] = useState(false);
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const sourceUrl = asset.fullUrl || asset.url;
  const posterUrl = asset.posterUrl || asset.thumbUrl;

  // Reset when the asset changes
  useEffect(() => {
    setErrored(false);
    setPlaying(false);
    videoRef.current?.pause();
  }, [asset.fullUrl, asset.posterUrl, asset.status, asset.thumbUrl, asset.url]);

  const setPaused = () => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    setPlaying(false);
  };

  const togglePlayback = async () => {
    const video = videoRef.current;
    if (!video) return;

    if (playing) {
      setPaused();
      return;
    }

    try {
      await video.play();
      setPlaying(true);
    } catch {
      setPlaying(false);
    }
  };

  const handleTogglePlayback = async (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    await togglePlayback();
  };

  const handleVideoClick = async (event: ReactMouseEvent<HTMLVideoElement>) => {
    event.stopPropagation();
    await togglePlayback();
  };

  const handleContainerClick = () => {
    if (!sourceUrl) {
      onClick?.();
    }
  };

  return (
    <div
      className={`group relative overflow-hidden rounded-xl border border-border bg-surface-2 ${aspectClass}`}
      onClick={handleContainerClick}
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
      ) : sourceUrl ? (
        <video
          ref={videoRef}
          src={sourceUrl}
          poster={posterUrl}
          className={mediaFitClass(fit)}
          playsInline
          preload="metadata"
          onClick={handleVideoClick}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onError={() => {
            setErrored(true);
            setPlaying(false);
          }}
        />
      ) : posterUrl ? (
        <img
          src={posterUrl}
          alt="Video preview"
          className={mediaFitClass(fit)}
          loading="lazy"
          draggable={false}
          onError={() => setErrored(true)}
        />
      ) : (
        <div className="flex h-full items-center justify-center text-sm text-content-muted">Video</div>
      )}

      {/* Play / Pause toggle */}
      {asset.status !== "pending" && asset.status !== "failed" && !errored ? (
        <>
          {!playing ? (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <button
                type="button"
                aria-label="Play video with sound"
                className="pointer-events-auto inline-flex h-11 w-11 items-center justify-center rounded-full bg-black/55 text-white shadow-md backdrop-blur-sm transition-opacity"
                onClick={handleTogglePlayback}
              >
                <Play className="h-5 w-5 fill-white" />
              </button>
            </div>
          ) : (
            <div className="pointer-events-none absolute right-3 top-3">
              <button
                type="button"
                aria-label="Pause video"
                className="pointer-events-auto inline-flex h-10 w-10 items-center justify-center rounded-full bg-black/55 text-white shadow-md backdrop-blur-sm transition-opacity hover:bg-black/70"
                onClick={handleTogglePlayback}
              >
                <Pause className="h-4 w-4 fill-white" />
              </button>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

export function SwipeCarousel({
  media,
  aspectClass,
  fit = "cover",
  onClick,
}: {
  media: MediaAsset[];
  aspectClass: string;
  fit?: SwipeMediaFit;
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
      <MediaContent asset={current} fit={fit} />

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
  fit = "cover",
  onOpen,
}: {
  media: MediaAsset[];
  aspect?: "1/1" | "4/5" | "9/16" | "16/9";
  fit?: SwipeMediaFit;
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
    return <VideoHoverPreview asset={primaryVideoAsset} aspectClass={aspectClass} fit={fit} onClick={onOpen} />;
  }

  if (assets.length === 1) {
    return (
      <div
        className={`relative overflow-hidden rounded-xl border border-border bg-surface-2 ${aspectClass}`}
        onClick={onOpen}
        role="presentation"
      >
        <MediaContent asset={assets[0]} fit={fit} />
      </div>
    );
  }

  return <SwipeCarousel media={assets} aspectClass={aspectClass} fit={fit} onClick={onOpen} />;
}
