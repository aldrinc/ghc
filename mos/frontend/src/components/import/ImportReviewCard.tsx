import { Badge } from "@/components/ui/badge";
import { formatPageType } from "@/lib/siteFormatters";
import type { SiteImportDetail } from "@/types/storefrontTemplates";

export function ImportReviewCard({
  importDetail,
  isReviewOnly,
}: {
  importDetail: SiteImportDetail;
  isReviewOnly: boolean;
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-content">
            {isReviewOnly ? "Import review artifact" : "Site-level review"}
          </div>
          <div className="text-xs text-content-muted">
            {isReviewOnly
              ? "Stored as a standard screenshot-to-code import review item."
              : "Adapter-backed family, entry page, completeness, and imported page set."}
          </div>
        </div>
        {!isReviewOnly && importDetail.savedSiteId ? <Badge tone="success">Saved</Badge> : null}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
          <div className="font-semibold text-content">
            {isReviewOnly ? "Suggested family" : "Resolved family"}
          </div>
          <div className="mt-1">
            {importDetail.resolvedSiteFamily || importDetail.suggestedTemplateFamily || "Unresolved"}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
          <div className="font-semibold text-content">Family hint</div>
          <div className="mt-1">{importDetail.siteFamilyHint || "None"}</div>
        </div>
        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
          <div className="font-semibold text-content">
            {isReviewOnly ? "Target page type" : "Entry page"}
          </div>
          <div className="mt-1">
            {String(
              importDetail.adaptedSite?.entry_page_type ||
                importDetail.adaptedSite?.entryPageType ||
                importDetail.resolvedPageType ||
                "Unknown"
            )}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
          <div className="font-semibold text-content">
            {isReviewOnly ? "Artifact mode" : "Completeness"}
          </div>
          <div className="mt-1">
            {isReviewOnly
              ? "Review only"
              : String(
                  importDetail.adaptedSite?.completeness_state ||
                    importDetail.adaptedSite?.completenessState ||
                    "partial"
                )}
          </div>
        </div>
        {!isReviewOnly ? (
          <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
            <div className="font-semibold text-content">Imported pages</div>
            <div className="mt-1">{importDetail.adaptedPages.length || 0}</div>
          </div>
        ) : null}
      </div>

      {isReviewOnly ? (
        <div className="mt-3 rounded-xl border border-accent/30 bg-accent/5 px-3 py-3 text-sm text-content-muted">
          Use the normalized sections and synthesis coverage below, then run{" "}
          <span className="font-semibold text-content">Convert to Draft</span>. Archive imports do not
          create a Site runtime page set.
        </div>
      ) : importDetail.adaptedPages.length > 0 ? (
        <div className="mt-3 space-y-2">
          {importDetail.adaptedPages.map((page, index) => {
            const pageType = String(page.page_type || page.pageType || `page_${index + 1}`);
            const templateId = String(page.template_id || page.templateId || "unmapped");
            const outboundLinks = Array.isArray(page.outbound_links || page.outboundLinks)
              ? (page.outbound_links || page.outboundLinks)
              : [];
            return (
              <div
                key={`${pageType}-${index}`}
                className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-content">{formatPageType(pageType)}</div>
                    <div className="mt-1">Template: {templateId}</div>
                  </div>
                  <Badge tone="neutral">#{index + 1}</Badge>
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <div>
                    <span className="font-semibold text-content">Slug:</span> {String(page.slug || "-")}
                  </div>
                  <div>
                    <span className="font-semibold text-content">Links:</span>{" "}
                    {(outboundLinks as unknown[]).length}
                  </div>
                  <div>
                    <span className="font-semibold text-content">Generated code:</span>{" "}
                    {page.generated_code || page.generatedCode ? "Available" : "Unavailable"}
                  </div>
                  <div>
                    <span className="font-semibold text-content">Puck data:</span>{" "}
                    {Object.keys(
                      (page.puck_data || page.puckData || {}) as Record<string, unknown>
                    ).length
                      ? "Available"
                      : "Unavailable"}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-3 rounded-xl border border-dashed border-border px-3 py-4 text-sm text-content-muted">
          No adapter-backed page set is available yet.
        </div>
      )}
    </div>
  );
}
