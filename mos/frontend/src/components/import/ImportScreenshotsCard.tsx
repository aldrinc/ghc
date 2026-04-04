import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { SiteImportSnapshot } from "@/types/storefrontTemplates";

export function ImportScreenshotsCard({
  snapshot,
  defaultOpen = false,
}: {
  snapshot: SiteImportSnapshot | null | undefined;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  if (!snapshot) return null;
  if (!snapshot.desktopScreenshotDataUrl && !snapshot.mobileScreenshotDataUrl) return null;

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between gap-2"
      >
        <div className="text-sm font-semibold text-content">Screenshots</div>
        {open ? (
          <ChevronDown className="h-4 w-4 text-content-muted" />
        ) : (
          <ChevronRight className="h-4 w-4 text-content-muted" />
        )}
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          {snapshot.desktopScreenshotDataUrl ? (
            <div>
              <div className="text-xs font-semibold text-content-muted">Desktop</div>
              <div className="mt-1 overflow-hidden rounded-lg border border-border">
                <img
                  src={snapshot.desktopScreenshotDataUrl}
                  alt="Desktop snapshot"
                  className="w-full"
                />
              </div>
            </div>
          ) : null}
          {snapshot.mobileScreenshotDataUrl ? (
            <div>
              <div className="text-xs font-semibold text-content-muted">Mobile</div>
              <div className="mt-1 overflow-hidden rounded-lg border border-border">
                <img
                  src={snapshot.mobileScreenshotDataUrl}
                  alt="Mobile snapshot"
                  className="w-full max-w-[200px]"
                />
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
