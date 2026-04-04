import { Dialog } from "@base-ui/react/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { floatingBackdrop } from "@/components/ui/floating";
import type { AdReviewItem } from "@/types/creativeReview";
import type { PaidAdsQaFinding } from "@/api/paidAdsQa";
import { PlatformPreviewShell } from "./PlatformPreviewShell";
import { ViolationBanner } from "./ViolationBanner";

// ---------------------------------------------------------------------------
// Finding row
// ---------------------------------------------------------------------------

const severityTone = {
  blocker: "danger",
  high: "danger",
  medium: "accent",
  low: "neutral",
} as const;

function FindingRow({ finding }: { finding: PaidAdsQaFinding }) {
  return (
    <div className="border-b border-border px-4 py-3 last:border-b-0">
      <div className="flex items-start gap-2">
        <Badge tone={severityTone[finding.severity]}>{finding.severity}</Badge>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-content">{finding.title}</div>
          <div className="mt-0.5 text-xs text-content-muted">{finding.message}</div>
          {finding.fixGuidance.length > 0 ? (
            <div className="mt-2 space-y-1">
              {finding.fixGuidance.map((tip, idx) => (
                <div key={idx} className="text-xs text-content-muted">
                  {tip}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ad copy section
// ---------------------------------------------------------------------------

function AdCopySection({ item }: { item: AdReviewItem }) {
  const fields = [
    { label: "Primary text", value: item.primaryText },
    { label: "Headline", value: item.headline },
    { label: "Description", value: item.description },
    { label: "CTA", value: item.cta },
    { label: "Destination URL", value: item.destinationUrl },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="text-sm font-semibold text-content">Ad copy</div>
        {item.copySource === "creative_spec" ? (
          <Badge tone="success">From spec</Badge>
        ) : item.copySource === "swipe_copy_pack" ? (
          <Badge tone="accent">Swipe copy</Badge>
        ) : (
          <Badge tone="neutral">No copy</Badge>
        )}
      </div>
      <div className="space-y-2">
        {fields.map(({ label, value }) => (
          <div key={label}>
            <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-content-muted">
              {label}
            </div>
            <div className="mt-0.5 whitespace-pre-wrap text-sm text-content">
              {value || <span className="italic text-content-muted">—</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Context section
// ---------------------------------------------------------------------------

function ContextSection({ item }: { item: AdReviewItem }) {
  const rows = [
    { label: "Experiment", value: item.experimentName },
    { label: "Variant", value: item.variantName },
    { label: "Angle", value: item.angle },
    { label: "Hook", value: item.hook },
    { label: "Funnel stage", value: item.funnelStage },
    { label: "Selected variation", value: item.selectedVariation },
    { label: "Source swipe", value: item.sourceSwipeLabel },
    { label: "Generation group", value: item.generationGroup },
    { label: "Asset ID", value: item.assetId },
    { label: "Spec ID", value: item.specId },
    { label: "Created", value: item.createdAt ? new Date(item.createdAt).toLocaleString() : null },
  ].filter((r) => r.value);

  if (!rows.length) return null;

  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-content">Context</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {rows.map(({ label, value }) => (
          <div key={label}>
            <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-content-muted">
              {label}
            </div>
            <div className="mt-0.5 truncate text-xs text-content" title={value ?? undefined}>
              {value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AdDetailPanel
// ---------------------------------------------------------------------------

/**
 * Slide-over panel showing full ad detail: platform preview, ad copy,
 * context metadata, and QA findings.
 */
export function AdDetailPanel({
  item,
  open,
  onClose,
  onExclude,
}: {
  item: AdReviewItem | null;
  open: boolean;
  onClose: () => void;
  onExclude?: (assetId: string) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(value) => !value && onClose()}>
      <Dialog.Portal>
        <Dialog.Backdrop className={floatingBackdrop()} />
        <Dialog.Viewport className="fixed inset-0 z-dialog flex justify-end">
          <Dialog.Popup
            className={cn(
              "relative flex h-full w-full max-w-2xl flex-col overflow-hidden",
              "border-l border-border bg-surface shadow-xl",
              "animate-in slide-in-from-right duration-200",
            )}
          >
            {item ? (
              <>
                {/* Header */}
                <div className="flex items-center justify-between border-b border-border px-6 py-4">
                  <div className="min-w-0">
                    <div className="truncate text-base font-semibold text-content">
                      {item.headline || `Asset ${item.assetId.slice(0, 8)}`}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2">
                      <ViolationBanner violations={item.violations} />
                      {item.publishDecision === "excluded" ? (
                        <Badge tone="neutral">Excluded</Badge>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {onExclude && item.publishDecision !== "excluded" ? (
                      <Button
                        variant="secondary"
                        size="xs"
                        onClick={() => onExclude(item.assetId)}
                      >
                        Exclude
                      </Button>
                    ) : null}
                    <Dialog.Close render={<Button variant="ghost" size="xs">Close</Button>} />
                  </div>
                </div>

                {/* Scrollable body */}
                <div className="flex-1 overflow-y-auto">
                  <div className="space-y-6 p-6">
                    {/* Platform preview */}
                    <PlatformPreviewShell
                      platform={item.platform}
                      imageUrl={item.imageUrl}
                      imageAlt={item.imageAlt}
                      primaryText={item.primaryText}
                      headline={item.headline}
                      description={item.description}
                      cta={item.cta}
                      destinationUrl={item.destinationUrl}
                      specReady={item.specReady}
                    />

                    {/* Ad copy */}
                    <AdCopySection item={item} />

                    {/* Context */}
                    <ContextSection item={item} />

                    {/* QA Findings */}
                    {item.findings.length > 0 ? (
                      <div className="space-y-2">
                        <div className="text-sm font-semibold text-content">
                          QA findings ({item.findings.length})
                        </div>
                        <div className="overflow-hidden rounded-lg border border-border">
                          {item.findings.map((finding) => (
                            <FindingRow key={finding.id} finding={finding} />
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </>
            ) : null}
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
