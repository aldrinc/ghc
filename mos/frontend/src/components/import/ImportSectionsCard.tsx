import { AlertTriangle, CheckCircle2, Layers3 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { NormalizedSection, SynthesisOutput } from "@/types/storefrontTemplates";

export function ImportSectionsCard({
  sections,
  selectedSectionIds,
  onToggleSection,
  onSelectAll,
  onClearAll,
  synthesis,
}: {
  sections: NormalizedSection[];
  selectedSectionIds: string[];
  onToggleSection: (sectionId: string) => void;
  onSelectAll: () => void;
  onClearAll: () => void;
  synthesis: SynthesisOutput | null | undefined;
}) {
  if (!sections.length) return null;

  return (
    <div className="space-y-4">
      {/* Section Selection */}
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">Normalized sections</div>
            <div className="text-xs text-content-muted">
              {selectedSectionIds.length} of {sections.length} selected
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={onSelectAll}>
              Select all
            </Button>
            <Button size="sm" variant="outline" onClick={onClearAll}>
              Clear
            </Button>
          </div>
        </div>
        <div className="mt-3 space-y-2">
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => onToggleSection(section.id)}
              className={cn(
                "w-full rounded-xl border px-3 py-2 text-left transition-colors",
                selectedSectionIds.includes(section.id)
                  ? "border-accent bg-accent/5"
                  : "border-border bg-surface-2"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold text-content">{section.sectionType}</div>
                  <div className="text-xs text-content-muted">
                    Confidence: {(section.confidence * 100).toFixed(0)}%
                  </div>
                </div>
                {selectedSectionIds.includes(section.id) ? (
                  <CheckCircle2 className="h-4 w-4 text-accent" />
                ) : (
                  <div className="h-4 w-4 rounded-full border border-border" />
                )}
              </div>
              {section.keyText && section.keyText.length > 0 && (
                <div className="mt-2 text-xs text-content-muted">
                  {section.keyText.slice(0, 2).join(", ")}
                  {section.keyText.length > 2 && ` +${section.keyText.length - 2} more`}
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Synthesis Output */}
      {synthesis && (
        <>
          {/* Block Coverage Summary */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-content">
              <Layers3 className="h-4 w-4 text-accent" />
              Block coverage
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
                <div className="text-xs text-content-muted">Coverage Score</div>
                <div className="mt-1 text-xl font-bold text-content">
                  {(synthesis.blockCoverage.coverageScore * 100).toFixed(0)}%
                </div>
              </div>
              <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
                <div className="text-xs text-content-muted">Exact Matches</div>
                <div className="mt-1 text-xl font-bold text-success">
                  {synthesis.blockCoverage.exactMatches}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
                <div className="text-xs text-content-muted">Partial Matches</div>
                <div className="mt-1 text-xl font-bold text-warning">
                  {synthesis.blockCoverage.partialMatches}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
                <div className="text-xs text-content-muted">Missing</div>
                <div className="mt-1 text-xl font-bold text-danger">
                  {synthesis.blockCoverage.missingMatches}
                </div>
              </div>
            </div>
          </div>

          {/* Mapped Blocks */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="text-sm font-semibold text-content">Mapped blocks</div>
            <div className="mt-3 space-y-2">
              {synthesis.blockCoverageDetails.map((detail) => (
                <div key={detail.sectionId} className="rounded-xl border border-border bg-surface-2 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold text-content">{detail.sectionType}</div>
                      <div className="text-xs text-content-muted">
                        {detail.mappedBlock ? `Mapped to: ${detail.mappedBlock}` : "No mapping"}
                      </div>
                    </div>
                    <Badge
                      tone={
                        detail.coverage === "exact"
                          ? "success"
                          : detail.coverage === "partial"
                            ? "warning"
                            : "danger"
                      }
                    >
                      {detail.coverage}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Missing Block Requests */}
          {synthesis.missingBlockRequests.length > 0 && (
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-content">
                <AlertTriangle className="h-4 w-4 text-warning" />
                Missing block requests
              </div>
              <div className="mt-3 space-y-2">
                {synthesis.missingBlockRequests.map((request) => (
                  <div key={request.requestId} className="rounded-xl border border-warning/30 bg-warning/5 px-3 py-2">
                    <div className="text-sm font-semibold text-content">{request.sectionType}</div>
                    <div className="mt-1 text-xs text-content-muted">{request.reason}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Badge tone="neutral">Family: {request.suggestedFamily}</Badge>
                      <Badge tone="neutral">Page: {request.suggestedPageType}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Synthesis Preview */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="text-sm font-semibold text-content">Synthesis preview</div>
            <div className="mt-3 space-y-2 text-xs text-content-muted">
              <div>
                <span className="font-semibold text-content">Target family:</span>{" "}
                {synthesis.targetFamily}
              </div>
              <div>
                <span className="font-semibold text-content">Page type:</span>{" "}
                {synthesis.targetPageType}
              </div>
              <div>
                <span className="font-semibold text-content">Puck data:</span>{" "}
                {Object.keys(synthesis.synthesizedPuckData).length > 0
                  ? "Available (structured)"
                  : "Not available"}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
