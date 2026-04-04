import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/layout/EmptyState";
import { formatImportStatus, formatPageType } from "@/lib/siteFormatters";
import { isImportActiveStatus, isReviewOnlyImport, readQueryError, resolveFamilyDefaults } from "./importUtils";
import {
  useSiteImportDetail,
  useSiteImportSnapshot,
  useSiteImports,
} from "@/api/storefrontTemplates";
import { ImportActivityPanel } from "./ImportActivityPanel";
import { ImportProgressCard } from "./ImportProgressCard";
import { ImportScreenshotsCard } from "./ImportScreenshotsCard";
import { ImportReviewCard } from "./ImportReviewCard";
import { ImportThemeCandidateCard } from "./ImportThemeCandidateCard";
import { ImportSectionsCard } from "./ImportSectionsCard";
import { SaveSiteImportCard } from "./SaveSiteImportCard";
import { ConvertToDraftCard } from "./ConvertToDraftCard";
import type { UpstreamTranscriptEntry, UpstreamVariantData } from "@/types/importActivity";
import type { SiteImportSummary } from "@/types/storefrontTemplates";

function formatImportModelLabel(modelId?: string, modelSlot?: number): string | undefined {
  if (modelId) return modelId;
  if (modelSlot === 1) return "Slot 1 · Gemini";
  if (modelSlot === 2) return "Slot 2 · Claude Opus";
  return undefined;
}

export function ImportDetailPanel({
  importId,
  workspaceId,
  imports,
  onSiteSaved,
  onDraftConverted,
}: {
  importId: string;
  workspaceId: string;
  imports: SiteImportSummary[];
  onSiteSaved: () => void;
  onDraftConverted: (variantId: string) => void;
}) {
  const [selectedSectionIds, setSelectedSectionIds] = useState<string[]>([]);
  const [defaultSectionSelectionImportId, setDefaultSectionSelectionImportId] = useState<string | null>(null);
  const [showActivity, setShowActivity] = useState(false);

  // Derive convert defaults from the selected import summary
  const importSummary = imports.find((item) => item.id === importId);
  const defaults = resolveFamilyDefaults(importSummary?.suggestedTemplateFamily);

  const { data: importDetail, error: importDetailError, refetch: refetchImportDetail } = useSiteImportDetail(
    importId,
    workspaceId,
    defaults.family,
    defaults.pageType,
    selectedSectionIds.length > 0 ? selectedSectionIds : undefined
  );
  const { data: importSnapshot } = useSiteImportSnapshot(importId, workspaceId);
  const { refetch: refetchImports } = useSiteImports(workspaceId);

  const isActive = isImportActiveStatus(importDetail?.status);
  const reviewOnly = isReviewOnlyImport(importDetail);

  // Reset section selection when import changes
  useEffect(() => {
    setSelectedSectionIds([]);
    setDefaultSectionSelectionImportId(null);
  }, [importId]);

  // Auto-select all sections when detail first loads
  useEffect(() => {
    if (!importDetail?.normalizedSections?.length) return;
    if (defaultSectionSelectionImportId === importId) return;
    setSelectedSectionIds(importDetail.normalizedSections.map((s) => s.id));
    setDefaultSectionSelectionImportId(importId);
  }, [defaultSectionSelectionImportId, importDetail, importId]);

  // Auto-expand activity when import is active, collapse when done
  useEffect(() => {
    setShowActivity(isActive);
  }, [isActive]);

  // Poll while active
  useEffect(() => {
    if (!isActive) return;
    const intervalId = window.setInterval(() => {
      void refetchImports();
      void refetchImportDetail();
    }, 1500);
    return () => window.clearInterval(intervalId);
  }, [isActive, refetchImportDetail, refetchImports]);

  // Build activity transcript
  const activityTranscript = useMemo<UpstreamTranscriptEntry[]>(() => {
    if (!importDetail?.upstreamTranscript) return [];
    return importDetail.upstreamTranscript.map((entry, index) => {
      const typedEntry = entry as Record<string, unknown>;
      const capturedAt = typeof typedEntry.capturedAt === "string" ? typedEntry.capturedAt : undefined;
      return {
        type: String(typedEntry.type || "status") as UpstreamTranscriptEntry["type"],
        value: typeof typedEntry.value === "string" ? typedEntry.value : undefined,
        data: typedEntry.data,
        eventId: typeof typedEntry.eventId === "string" ? typedEntry.eventId : undefined,
        variantIndex: Number(typedEntry.variantIndex ?? 0),
        timestamp: capturedAt ? new Date(capturedAt).getTime() : index,
      };
    });
  }, [importDetail?.upstreamTranscript]);

  const activityVariants = useMemo<UpstreamVariantData[]>(() => {
    if (!importDetail?.upstreamVariants) return [];
    const metadataModels = Array.isArray(importDetail.upstreamMetadata?.variantModels)
      ? (importDetail.upstreamMetadata.variantModels as string[])
      : [];
    return importDetail.upstreamVariants.map((variant, index) => {
      const typedVariant = variant as Record<string, unknown>;
      const variantIndex = Number(typedVariant.variantIndex ?? index);
      const variantEvents = activityTranscript.filter((event) => event.variantIndex === variantIndex);
      const firstEventTimestamp = variantEvents[0]?.timestamp;
      const terminalEvent = [...variantEvents]
        .reverse()
        .find((event) => event.type === "variantComplete" || event.type === "variantError");
      const modelSlot = typeof typedVariant.modelSlot === "number"
        ? typedVariant.modelSlot
        : typeof importDetail.modelSlots?.[variantIndex] === "number"
          ? importDetail.modelSlots[variantIndex]
          : undefined;
      const rawStatus = String(typedVariant.status || "pending");
      const status: UpstreamVariantData["status"] =
        rawStatus === "completed"
          ? "complete"
          : rawStatus === "failed"
            ? "error"
            : rawStatus === "pending"
              ? (isActive ? "generating" : "paused")
              : (rawStatus as UpstreamVariantData["status"]);
      const modelId = typeof typedVariant.modelId === "string"
        ? typedVariant.modelId
        : typeof typedVariant.model === "string"
          ? typedVariant.model
          : typeof metadataModels[variantIndex] === "string"
            ? metadataModels[variantIndex]
            : undefined;
      return {
        variantIndex,
        code: typeof typedVariant.code === "string" ? typedVariant.code : undefined,
        status,
        model: formatImportModelLabel(modelId, modelSlot),
        requestStartedAt: firstEventTimestamp,
        completedAt: terminalEvent?.timestamp,
      };
    });
  }, [activityTranscript, importDetail?.status, importDetail?.upstreamMetadata, importDetail?.upstreamVariants]);

  const toggleSection = (sectionId: string) => {
    setSelectedSectionIds((prev) =>
      prev.includes(sectionId) ? prev.filter((id) => id !== sectionId) : [...prev, sectionId]
    );
  };

  // Error state
  if (importDetailError) {
    return (
      <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-8 text-center text-sm text-danger">
        {readQueryError(importDetailError, "Failed to load import details.")}
      </div>
    );
  }

  // Loading state
  if (!importDetail) {
    return (
      <div className="rounded-2xl border border-border bg-surface px-4 py-8 text-center text-sm text-content-muted">
        Loading import details...
      </div>
    );
  }

  const isCompleted = importDetail.status === "completed";
  const isFailed = importDetail.status === "failed";
  const defaultSiteName = importDetail.title || importDetail.sourceHostname || "Imported Site";
  const defaultConvertName = importDetail.title || importDetail.sourceHostname || "Imported Variant";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">
              {importDetail.title || importDetail.sourceHostname || importDetail.sourceUrl}
            </div>
            <div className="mt-1 text-xs text-content-muted">{importDetail.sourceUrl}</div>
          </div>
          <Badge tone={formatImportStatus(importDetail.status)}>{importDetail.status}</Badge>
        </div>
      </div>

      {/* Failed: error prominent */}
      {isFailed && importDetail.captureError && (
        <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-danger">
            <AlertTriangle className="h-4 w-4" />
            Capture failed
          </div>
          <div className="mt-2 text-sm text-danger">{importDetail.captureError}</div>
        </div>
      )}

      {/* Always: progress card */}
      <ImportProgressCard importDetail={importDetail} />

      {/* Active: live activity panel (always open) */}
      {isActive && (
        <div className="rounded-2xl border border-border bg-surface px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-content">Generator activity</div>
              <div className="text-xs text-content-muted">Live screenshot-to-code progress.</div>
            </div>
            <div className="flex items-center gap-2 text-xs text-content-muted">
              <span>{importDetail.upstreamTranscript.length} events</span>
              <span>{importDetail.upstreamVariants.length} variants</span>
            </div>
          </div>
          <div className="mt-3">
            <ImportActivityPanel
              transcript={activityTranscript}
              variants={activityVariants}
              isActive={isActive}
            />
          </div>
        </div>
      )}

      {/* Completed / Failed: screenshots (collapsed by default) */}
      {!isActive && (
        <ImportScreenshotsCard snapshot={importSnapshot} defaultOpen={false} />
      )}

      {/* Completed: review panels */}
      {isCompleted && (
        <>
          <ImportReviewCard importDetail={importDetail} isReviewOnly={reviewOnly} />

          <ImportThemeCandidateCard themeCandidate={importDetail.themeCandidate} />

          <ImportSectionsCard
            sections={importDetail.normalizedSections || []}
            selectedSectionIds={selectedSectionIds}
            onToggleSection={toggleSection}
            onSelectAll={() => {
              if (importDetail.normalizedSections?.length) {
                setSelectedSectionIds(importDetail.normalizedSections.map((s) => s.id));
              }
            }}
            onClearAll={() => setSelectedSectionIds([])}
            synthesis={importDetail.synthesis}
          />

          {/* Completed: collapsed activity */}
          {!isActive && importDetail.upstreamTranscript.length > 0 && (
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <button
                type="button"
                onClick={() => setShowActivity((prev) => !prev)}
                className="flex w-full items-center justify-between gap-2"
              >
                <div className="flex items-center gap-2">
                  <div className="text-sm font-semibold text-content">Generator activity</div>
                  <span className="text-xs text-content-muted">
                    {importDetail.upstreamTranscript.length} events
                  </span>
                </div>
                {showActivity ? (
                  <ChevronDown className="h-4 w-4 text-content-muted" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-content-muted" />
                )}
              </button>
              {showActivity && (
                <div className="mt-3">
                  <ImportActivityPanel
                    transcript={activityTranscript}
                    variants={activityVariants}
                    isActive={false}
                  />
                  <div className="mt-4 rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                    <div className="font-semibold text-content">Generator metadata</div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <div>Generator: {String(importDetail.upstreamMetadata.generatorSystem || "screenshot-to-code")}</div>
                      <div>Stack: {String(importDetail.upstreamMetadata.stack || "react_tailwind")}</div>
                      <div>Variant count: {String(importDetail.upstreamMetadata.variantCount || importDetail.upstreamVariants.length)}</div>
                      <div>Models: {Array.isArray(importDetail.upstreamMetadata.variantModels) ? (importDetail.upstreamMetadata.variantModels as string[]).join(", ") : "-"}</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Action cards */}
          {!reviewOnly && (
            <SaveSiteImportCard
              importId={importId}
              workspaceId={workspaceId}
              savedSiteId={importDetail.savedSiteId}
              defaultSiteName={defaultSiteName}
              onSaved={() => {
                refetchImportDetail();
                onSiteSaved();
              }}
            />
          )}

          <ConvertToDraftCard
            importId={importId}
            workspaceId={workspaceId}
            selectedSectionIds={selectedSectionIds}
            defaultName={defaultConvertName}
            defaultFamily={defaults.family}
            defaultPageType={defaults.pageType}
            onConverted={(variantId) => {
              refetchImportDetail();
              onDraftConverted(variantId);
            }}
          />
        </>
      )}
    </div>
  );
}
