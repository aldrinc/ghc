import { useState } from "react";
import { ChevronDown, ChevronRight, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ThemeCandidate } from "@/types/storefrontTemplates";

export function ImportThemeCandidateCard({
  themeCandidate,
}: {
  themeCandidate: ThemeCandidate;
}) {
  const [open, setOpen] = useState(false);

  if (!themeCandidate || Object.keys(themeCandidate).length === 0) return null;

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between gap-2"
      >
        <div className="flex items-center gap-2 text-sm font-semibold text-content">
          <Sparkles className="h-4 w-4 text-accent" />
          Theme candidate
        </div>
        {open ? (
          <ChevronDown className="h-4 w-4 text-content-muted" />
        ) : (
          <ChevronRight className="h-4 w-4 text-content-muted" />
        )}
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          {themeCandidate.palette && (
            <div>
              <div className="text-xs font-semibold text-content-muted">Palette</div>
              <div className="mt-1 flex flex-wrap gap-2">
                {Object.entries(themeCandidate.palette)
                  .filter(([, v]) => v)
                  .map(([key, value]) => (
                    <div key={key} className="flex items-center gap-2 rounded-lg border border-border px-2 py-1">
                      <div
                        className="h-3 w-3 rounded-full border border-border"
                        style={{ backgroundColor: value || undefined }}
                      />
                      <span className="text-xs text-content-muted">{key}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
          {themeCandidate.fonts && (
            <div>
              <div className="text-xs font-semibold text-content-muted">Fonts</div>
              <div className="mt-1 flex flex-wrap gap-2">
                {Object.entries(themeCandidate.fonts)
                  .filter(([, v]) => v)
                  .map(([key, value]) => (
                    <Badge key={key} tone="neutral">
                      {key}: {value}
                    </Badge>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
