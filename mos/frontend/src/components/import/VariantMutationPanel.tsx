import { useEffect, useState } from "react";
import { CheckCircle2, RefreshCw, Wand2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatPageType } from "@/lib/siteFormatters";
import { readProvenanceString, readQueryError } from "./importUtils";
import {
  useGenerateVariants,
  useTemplateVariantDetail,
  useVariantPresets,
} from "@/api/storefrontTemplates";

export function VariantMutationPanel({
  variantId,
  workspaceId,
  onVariantGenerated,
}: {
  variantId: string;
  workspaceId?: string;
  onVariantGenerated: () => void;
}) {
  const [selectedPresets, setSelectedPresets] = useState<string[]>([]);
  const [generatedNames, setGeneratedNames] = useState<string[]>([]);

  const { data: variantDetail, isLoading: variantLoading, error: variantError } = useTemplateVariantDetail(
    variantId,
    workspaceId
  );
  const { data: presets = [], isLoading: presetsLoading, error: presetsError } = useVariantPresets(
    variantId,
    workspaceId
  );
  const generateVariants = useGenerateVariants();

  useEffect(() => {
    setSelectedPresets([]);
    setGeneratedNames([]);
  }, [variantId]);

  const togglePreset = (presetId: string) => {
    setSelectedPresets((prev) =>
      prev.includes(presetId) ? prev.filter((id) => id !== presetId) : [...prev, presetId]
    );
  };

  const handleGenerateVariants = async () => {
    if (!workspaceId || selectedPresets.length === 0) return;
    try {
      await generateVariants.mutateAsync({
        variantId,
        clientId: workspaceId,
        presetIds: selectedPresets,
        generatedNames: generatedNames.length === selectedPresets.length ? generatedNames : undefined,
      });
      onVariantGenerated();
    } catch (err) {
      console.error("Failed to generate variants:", err);
    }
  };

  if (variantLoading || presetsLoading) {
    return (
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="text-sm text-content-muted">Loading variant presets...</div>
      </div>
    );
  }

  if (variantError || presetsError) {
    return (
      <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-4">
        <div className="text-sm text-danger">
          {readQueryError(variantError || presetsError, "Failed to load variant presets.")}
        </div>
      </div>
    );
  }

  const applicablePresets = presets.filter((p) => p.applicable);
  const notApplicablePresets = presets.filter((p) => !p.applicable);

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <div className="text-sm font-semibold text-content">Generate variants</div>
          <div className="text-xs text-content-muted">
            Apply mutation presets to create derived variants.
          </div>
        </div>
        <Wand2 className="h-4 w-4 text-accent" />
      </div>

      {variantDetail && (
        <div className="mt-4 rounded-xl border border-border bg-surface-2 px-3 py-3">
          <div className="text-sm font-semibold text-content">{variantDetail.name}</div>
          <div className="mt-1 text-xs text-content-muted">
            {variantDetail.family} / {formatPageType(variantDetail.pageType)}
          </div>
          {variantDetail.provenance && (() => {
            const provenance = variantDetail.provenance as Record<string, unknown>;
            const sourceType = readProvenanceString(provenance, "sourceType", "source_type");
            const parentVariantName = readProvenanceString(provenance, "parentVariantName", "parent_variant_name");
            const sourceUrl = readProvenanceString(provenance, "sourceUrl", "source_url");
            return (
              <div className="mt-2 text-xs text-content-muted">
                {sourceType === "variant_mutation" ? (
                  <span>Derived from: {parentVariantName || "Unknown"}</span>
                ) : (
                  <span>Source: {sourceUrl || "Import"}</span>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {applicablePresets.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-content">Available presets</div>
          {applicablePresets.map((preset) => (
            <button
              key={preset.presetId}
              type="button"
              onClick={() => togglePreset(preset.presetId)}
              className={cn(
                "w-full rounded-xl border px-3 py-2 text-left transition-colors",
                selectedPresets.includes(preset.presetId)
                  ? "border-accent bg-accent/5"
                  : "border-border bg-surface-2 hover:border-accent/40"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold text-content">{preset.presetLabel}</div>
                  <div className="mt-1 text-xs text-content-muted">{preset.presetDescription}</div>
                </div>
                {selectedPresets.includes(preset.presetId) ? (
                  <CheckCircle2 className="h-4 w-4 text-accent" />
                ) : (
                  <div className="h-4 w-4 rounded-full border border-border" />
                )}
              </div>
              {preset.effects.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {preset.effects.slice(0, 2).map((effect) => (
                    <Badge key={effect} tone="neutral" className="text-[10px]">
                      {effect}
                    </Badge>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {notApplicablePresets.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-content-muted">Not applicable</div>
          {notApplicablePresets.map((preset) => (
            <div
              key={preset.presetId}
              className="rounded-xl border border-border bg-surface-2/50 px-3 py-2 opacity-60"
            >
              <div className="text-sm font-semibold text-content">{preset.presetLabel}</div>
              <div className="mt-1 text-xs text-content-muted">{preset.notApplicableReason}</div>
            </div>
          ))}
        </div>
      )}

      {presets.length === 0 && (
        <div className="mt-4 rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted">
          No mutation presets available for this variant.
        </div>
      )}

      {selectedPresets.length > 0 && (
        <div className="mt-4 space-y-3">
          <Button
            onClick={handleGenerateVariants}
            disabled={generateVariants.isPending || !workspaceId}
            className="w-full"
          >
            {generateVariants.isPending ? (
              <>
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Wand2 className="mr-2 h-4 w-4" />
                Generate {selectedPresets.length} {selectedPresets.length === 1 ? "variant" : "variants"}
              </>
            )}
          </Button>
          {generateVariants.isError && (
            <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
              Failed to generate variants. Please try again.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
