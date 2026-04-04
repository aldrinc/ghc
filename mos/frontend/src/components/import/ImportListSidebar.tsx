import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatImportStatus, formatPageType } from "@/lib/siteFormatters";
import type { SiteImportSummary, TemplateVariantSummary } from "@/types/storefrontTemplates";

export function ImportListSidebar({
  imports,
  isLoading,
  selectedImportId,
  onSelectImport,
  variants,
  selectedVariantId,
  onSelectVariant,
  lastConvertedVariantId,
}: {
  imports: SiteImportSummary[];
  isLoading: boolean;
  selectedImportId: string | null;
  onSelectImport: (importId: string) => void;
  variants: TemplateVariantSummary[];
  selectedVariantId: string | null;
  onSelectVariant: (variantId: string) => void;
  lastConvertedVariantId: string | null;
}) {
  return (
    <div className="space-y-4">
      {/* Import History */}
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
          <div>
            <div className="text-sm font-semibold text-content">Import history</div>
            <div className="text-xs text-content-muted">Previously imported reference sites.</div>
          </div>
          <Badge tone="neutral">{imports.length} imports</Badge>
        </div>

        <div className="mt-4 space-y-2">
          {isLoading ? (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted">
              Loading imports...
            </div>
          ) : !imports.length ? (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted">
              No imports yet. Use the form above to import a reference site.
            </div>
          ) : (
            imports.map((imp) => {
              const selected = imp.id === selectedImportId;
              return (
                <button
                  key={imp.id}
                  type="button"
                  onClick={() => onSelectImport(imp.id)}
                  className={cn(
                    "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                    selected
                      ? "border-accent bg-accent/5"
                      : "border-border bg-surface-2 hover:border-accent/40"
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-content">
                        {imp.title || imp.sourceHostname || imp.sourceUrl}
                      </div>
                      <div className="mt-1 truncate text-xs text-content-muted">{imp.sourceUrl}</div>
                    </div>
                    <Badge tone={formatImportStatus(imp.status)}>{imp.status}</Badge>
                  </div>
                  <div className="mt-2 flex items-center gap-3 text-xs text-content-muted">
                    <span>{imp.suggestedTemplateFamily || "No suggestion"}</span>
                    <span>{new Date(imp.createdAt).toLocaleDateString()}</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Draft Variants */}
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
          <div>
            <div className="text-sm font-semibold text-content">Draft variants</div>
            <div className="text-xs text-content-muted">Template variants created from imports.</div>
          </div>
          <Badge tone="neutral">{variants.length} variants</Badge>
        </div>

        <div className="mt-4 space-y-2">
          {!variants.length ? (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted">
              No draft variants yet. Convert an import to create one.
            </div>
          ) : (
            variants.map((variant) => (
              <button
                key={variant.id}
                type="button"
                onClick={() => onSelectVariant(variant.id)}
                className={cn(
                  "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                  selectedVariantId === variant.id
                    ? "border-accent bg-accent/5"
                    : "border-border bg-surface-2 hover:border-accent/40"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-content">{variant.name}</div>
                    <div className="mt-1 text-xs text-content-muted">
                      {variant.family} / {formatPageType(variant.pageType)}
                    </div>
                    {(variant.siteImportId === selectedImportId ||
                      variant.id === lastConvertedVariantId ||
                      variant.mutationPresetLabel) && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {variant.siteImportId === selectedImportId && (
                          <Badge tone="accent">From this import</Badge>
                        )}
                        {variant.id === lastConvertedVariantId && (
                          <Badge tone="success">Just created</Badge>
                        )}
                        {variant.mutationPresetLabel && (
                          <Badge tone="accent">{variant.mutationPresetLabel}</Badge>
                        )}
                      </div>
                    )}
                  </div>
                  <Badge tone={variant.status === "draft" ? "warning" : "success"}>
                    {variant.status}
                  </Badge>
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
