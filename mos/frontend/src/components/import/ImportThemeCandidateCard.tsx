import { useState } from "react";
import { ChevronDown, ChevronRight, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ThemeCandidate } from "@/types/storefrontTemplates";

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

export function ImportThemeCandidateCard({
  themeCandidate,
}: {
  themeCandidate: ThemeCandidate;
}) {
  const [open, setOpen] = useState(false);
  const cssVars = themeCandidate.cssVars ?? {};
  const fontUrls = readStringList(themeCandidate.fontUrls);
  const missingFields = readStringList(themeCandidate.diagnostics?.promotionReadiness?.missingFields);
  const promotionNotes = readStringList(themeCandidate.diagnostics?.promotionReadiness?.notes);
  const sourcePath = readString(themeCandidate.diagnostics?.sourceInputs?.designSystemHtmlPath);
  const fontDelivery = readString(themeCandidate.diagnostics?.fidelity?.fontDelivery);
  const backgroundStrategy = readString(themeCandidate.diagnostics?.fidelity?.backgroundStrategy);

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
          <div className="flex flex-wrap gap-2">
            {readString(themeCandidate.dataTheme) && <Badge tone="neutral">theme: {themeCandidate.dataTheme}</Badge>}
            {Object.keys(cssVars).length > 0 && <Badge tone="neutral">css vars: {Object.keys(cssVars).length}</Badge>}
            {fontUrls.length > 0 && <Badge tone="neutral">font urls: {fontUrls.length}</Badge>}
            {readString(themeCandidate.fontCss) && <Badge tone="neutral">font css: inline</Badge>}
            {themeCandidate.brand?.name && <Badge tone="neutral">brand: {themeCandidate.brand.name}</Badge>}
          </div>
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
          {(sourcePath || fontDelivery || backgroundStrategy) && (
            <div className="space-y-1">
              <div className="text-xs font-semibold text-content-muted">Extraction</div>
              {sourcePath && <div className="text-xs text-content-muted">source: <code>{sourcePath}</code></div>}
              {fontDelivery && <div className="text-xs text-content-muted">font delivery: {fontDelivery}</div>}
              {backgroundStrategy && <div className="text-xs text-content-muted">backgrounds: {backgroundStrategy}</div>}
            </div>
          )}
          {(missingFields.length > 0 || promotionNotes.length > 0) && (
            <div className="space-y-1">
              <div className="text-xs font-semibold text-content-muted">Promotion</div>
              {missingFields.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {missingFields.map((field) => (
                    <Badge key={field} tone="neutral">
                      missing: {field}
                    </Badge>
                  ))}
                </div>
              )}
              {promotionNotes.map((note) => (
                <div key={note} className="text-xs text-content-muted">
                  {note}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
