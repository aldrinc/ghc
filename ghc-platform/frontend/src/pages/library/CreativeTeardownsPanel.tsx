import { useEffect, useMemo, useState } from "react";
import { useTeardownApi } from "@/api/teardowns";
import { MediaTile, MediaViewer } from "@/components/library/MediaViewer";
import type { MediaAsset } from "@/types/library";
import type { Teardown } from "@/types/teardowns";

function ChannelBadge({ channel }: { channel?: string }) {
  if (!channel) return null;
  return (
    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-slate-700">
      {channel.replace(/_/g, " ")}
    </span>
  );
}

function ScorePill({ score }: { score?: number }) {
  if (score === undefined || score === null) return null;
  const hue = Math.max(0, Math.min(120, (score / 10) * 120));
  const bg = `hsla(${hue}, 70%, 90%, 1)`;
  const text = `hsla(${hue}, 60%, 30%, 1)`;
  return (
    <span className="rounded-full px-2 py-0.5 text-xs font-semibold" style={{ backgroundColor: bg, color: text }}>
      Hook {score}/10
    </span>
  );
}

const videoExtensions = [".mp4", ".mov", ".webm", ".mkv", ".m4v", ".mpg", ".mpeg"];

function isLikelyVideoUrl(url?: string) {
  if (!url) return false;
  const lower = url.toLowerCase();
  const path = lower.split(/[?#]/)[0];
  if (videoExtensions.some((ext) => path.endsWith(ext))) return true;
  return lower.includes("video/mp4") || lower.includes("mime=video");
}

function teardownMedia(teardown: Teardown): MediaAsset[] {
  const url = teardown.primary_media_asset_url;
  if (!url) return [];
  const isVideo = isLikelyVideoUrl(url);
  if (isVideo) {
    return [{ type: "video", url }];
  }
  return [
    {
      type: "image",
      url,
      thumbUrl: url,
      alt: teardown.one_liner || teardown.brand_name || "Creative preview",
    },
  ];
}

function TeardownCard({ teardown }: { teardown: Teardown }) {
  const [open, setOpen] = useState(false);
  const observed = teardown.captured_at ? new Date(teardown.captured_at).toLocaleDateString() : "Unknown";
  const media = useMemo(() => teardownMedia(teardown), [teardown]);
  const primary = media[0];

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="ds-card ds-card--md ds-card--interactive shadow-none hover:shadow-none flex w-full flex-col gap-3 text-left"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-content">{teardown.brand_name || "Unknown brand"}</div>
            <div className="text-xs text-content-muted">
              Creative {teardown.creative_fingerprint?.slice(0, 8) ?? teardown.creative_id.slice(0, 8)}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ChannelBadge channel={teardown.channel} />
            <ScorePill score={teardown.hook_score} />
          </div>
        </div>

        <MediaTile asset={primary} count={media.length} />

        <div className="space-y-1">
          {teardown.one_liner && <div className="text-sm font-medium text-content">“{teardown.one_liner}”</div>}
          {teardown.algorithmic_thesis && (
            <p className="line-clamp-3 text-sm text-content-muted">{teardown.algorithmic_thesis}</p>
          )}
        </div>

        <div className="flex items-center justify-between text-xs text-content-muted">
          <span>Captured {observed}</span>
          <span className="font-medium text-content">{teardown.funnel_stage || "unassigned"}</span>
        </div>
      </button>

      <MediaViewer
        assets={media}
        open={open}
        onClose={() => setOpen(false)}
        title={teardown.brand_name || "Creative teardown"}
      />
    </>
  );
}

function LoadingGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div
          key={idx}
          className="ds-card ds-card--md flex flex-col gap-3 shadow-none animate-pulse"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="h-3 w-24 rounded bg-muted" />
            <div className="h-4 w-10 rounded-full bg-muted" />
          </div>
          <div className="h-36 w-full rounded-lg bg-muted" />
          <div className="space-y-2">
            <div className="h-3 w-3/4 rounded bg-muted" />
            <div className="h-3 w-full rounded bg-muted" />
            <div className="h-3 w-2/3 rounded bg-muted" />
          </div>
          <div className="flex items-center justify-between text-xs text-content-muted">
            <div className="h-3 w-20 rounded bg-muted" />
            <div className="h-3 w-12 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function CreativeTeardownsPanel() {
  const { listTeardowns } = useTeardownApi();
  const [teardowns, setTeardowns] = useState<Teardown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listTeardowns({ limit: 24, includeChildren: false })
      .then((data) => {
        if (cancelled) return;
        setTeardowns(data);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || "Failed to load teardowns");
        setTeardowns([]);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [listTeardowns]);

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-xl font-semibold text-content">Creative Teardowns</h2>
          <p className="text-sm text-content-muted">
            Canonical teardown cards built from deduped creatives (ad copy + media).
          </p>
        </div>
      </div>
      {error && <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      {loading && <LoadingGrid />}
      {!loading && teardowns.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {teardowns.map((t) => (
            <TeardownCard key={t.id} teardown={t} />
          ))}
        </div>
      )}
      {!loading && teardowns.length === 0 && !error && (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          No teardowns yet. Ingest ads and post teardowns to see them here.
        </div>
      )}
    </div>
  );
}
