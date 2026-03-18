import type { AdPlatformId, PlatformPreviewProps } from "@/types/adPlatform";
import { getPreviewRenderer } from "@/providers/previewRegistry";

/**
 * Resolves and renders the correct platform feed preview for a given ad.
 * Falls back to a basic image preview if no platform renderer is registered.
 */
export function PlatformPreviewShell({
  platform,
  ...previewProps
}: PlatformPreviewProps & { platform: AdPlatformId }) {
  const Renderer = getPreviewRenderer(platform);

  if (Renderer) {
    return <Renderer {...previewProps} />;
  }

  // Fallback: basic image + copy preview
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      {previewProps.imageUrl ? (
        <img
          src={previewProps.imageUrl}
          alt={previewProps.imageAlt}
          className="h-[320px] w-full object-contain border-b border-border bg-surface-2"
          loading="lazy"
        />
      ) : (
        <div className="flex h-[320px] items-center justify-center border-b border-border bg-surface-2 text-sm text-content-muted">
          No preview available
        </div>
      )}
      <div className="space-y-2 p-4">
        {previewProps.headline ? (
          <div className="text-sm font-semibold text-content">{previewProps.headline}</div>
        ) : null}
        {previewProps.primaryText ? (
          <div className="text-xs text-content-muted">{previewProps.primaryText}</div>
        ) : null}
        {previewProps.cta ? (
          <div className="inline-block rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
            {previewProps.cta}
          </div>
        ) : null}
      </div>
    </div>
  );
}
