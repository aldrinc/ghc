import { Badge } from "@/components/ui/badge";
import { formatImportStatus } from "@/lib/siteFormatters";
import type { SiteImportDetail } from "@/types/storefrontTemplates";

export function ImportProgressCard({ importDetail }: { importDetail: SiteImportDetail }) {
  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-content">Import progress</div>
          <div className="text-xs text-content-muted">
            Pipeline stage and status for this run.
          </div>
        </div>
        <Badge tone={formatImportStatus(importDetail.status)}>{importDetail.status}</Badge>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
          <div className="font-semibold text-content">Input mode</div>
          <div className="mt-1">{importDetail.inputMode || "image"}</div>
        </div>
        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
          <div className="font-semibold text-content">Model slots</div>
          <div className="mt-1">
            {importDetail.modelSlots.length ? importDetail.modelSlots.join(", ") : "Default slot set"}
          </div>
        </div>
      </div>
      {(importDetail.captureError || importDetail.generatorError) && (
        <div className="mt-3 rounded-xl border border-danger/30 bg-danger/5 px-3 py-3 text-sm text-danger">
          <div className="font-semibold">{importDetail.failureStage || "Import failed"}</div>
          <div className="mt-1">{importDetail.generatorError || importDetail.captureError}</div>
        </div>
      )}
    </div>
  );
}
