import { Dialog } from "@base-ui/react/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { floatingBackdrop } from "@/components/ui/floating";
import { SwipeMedia } from "@/components/library/SwipeMedia";
import { channelDisplayName } from "@/lib/channels";
import type { AssetReviewItem, ReviewStatus } from "@/types/assetReview";
import type { CompanySwipeAsset } from "@/types/swipes";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function reviewTone(status: ReviewStatus): "neutral" | "success" | "danger" | "warning" {
  switch (status) {
    case "approved":
      return "success";
    case "rejected":
      return "danger";
    case "stale_after_sync":
      return "warning";
    default:
      return "neutral";
  }
}

function reviewLabel(status: ReviewStatus): string {
  switch (status) {
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "stale_after_sync":
      return "Stale";
    default:
      return "Pending";
  }
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

// ---------------------------------------------------------------------------
// Section components
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-content-muted">
      {children}
    </div>
  );
}

function FieldRow({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <div className="mt-0.5 whitespace-pre-wrap text-sm text-content">
        {value != null && value !== "" ? value : <span className="italic text-content-muted">—</span>}
      </div>
    </div>
  );
}

function MetaCell({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <div className="mt-0.5 truncate text-xs text-content" title={String(value ?? "")}>
        {value != null && value !== "" ? value : "—"}
      </div>
    </div>
  );
}

function AdCopySection({ item }: { item: AssetReviewItem }) {
  const raw = item.raw as CompanySwipeAsset | undefined;
  return (
    <div className="space-y-3">
      <div className="text-sm font-semibold text-content">Ad copy</div>
      <div className="space-y-3">
        <FieldRow label="Headline" value={item.headline} />
        <FieldRow label="Body / Primary text" value={item.body} />
        <FieldRow label="CTA" value={item.ctaText} />
        <FieldRow label="Link description" value={raw?.link_description} />
      </div>
    </div>
  );
}

function PerformanceSection({ item }: { item: AssetReviewItem }) {
  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-content">Performance & tracking</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        <MetaCell label="Performance score" value={item.performanceScore} />
        <MetaCell label="Days active" value={item.daysActive} />
        <MetaCell label="Used count" value={item.usedCount} />
        <MetaCell
          label="Status"
          value={item.status === "active" ? "Active" : item.status === "inactive" ? "Inactive" : "—"}
        />
      </div>
      {item.platform.length ? (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {item.platform.map((p) => (
            <Badge key={p}>{channelDisplayName(p)}</Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SourceDatesSection({ item }: { item: AssetReviewItem }) {
  const raw = item.raw as CompanySwipeAsset | undefined;
  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-content">Source dates</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        <MetaCell label="First seen" value={formatDate(item.sourceFirstSeenAt)} />
        <MetaCell label="Last seen" value={formatDate(item.sourceLastSeenAt)} />
        <MetaCell label="Last synced" value={formatDate(item.sourceLastSyncedAt)} />
        <MetaCell label="Content changed" value={formatDate(raw?.source_content_changed_at)} />
      </div>
    </div>
  );
}

function AnalysisSection({ item }: { item: AssetReviewItem }) {
  const raw = item.raw as CompanySwipeAsset | undefined;
  if (!raw) return null;

  const rows = [
    { label: "Analysis status", value: raw.analysis_status },
    { label: "Analysis model", value: raw.analysis_model },
    { label: "Ad unit format", value: raw.ad_unit_format },
    { label: "Placement shape", value: raw.placement_shape },
    { label: "Channel", value: raw.channel },
    { label: "Hook type", value: raw.hook_type },
    { label: "Visual archetype", value: raw.visual_archetype },
    { label: "Funnel stage", value: raw.funnel_stage },
    { label: "Angle family", value: raw.angle_family },
    { label: "Product presence", value: raw.product_presence },
    { label: "Proof type", value: raw.proof_type },
    { label: "Claim risk", value: raw.claim_risk },
    { label: "Destination type", value: raw.destination_type },
  ].filter((r) => r.value);

  if (!rows.length) return null;

  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-content">Analysis</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        {rows.map(({ label, value }) => (
          <MetaCell key={label} label={label} value={value} />
        ))}
      </div>
      {raw.analysis_error ? (
        <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
          {raw.analysis_error}
        </div>
      ) : null}
    </div>
  );
}

function LandingPageSection({ item }: { item: AssetReviewItem }) {
  if (!item.destinationUrl) return null;
  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-content">Landing page</div>
      <a
        href={item.destinationUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="block truncate text-sm text-accent underline underline-offset-2"
        title={item.destinationUrl}
      >
        {item.destinationHostname || item.destinationUrl}
      </a>
    </div>
  );
}

function RawPayloadSection({ item }: { item: AssetReviewItem }) {
  return (
    <details className="group">
      <summary className="cursor-pointer select-none text-sm font-semibold text-content">
        Raw payload
      </summary>
      <pre className="mt-2 max-h-96 overflow-auto rounded-lg border border-border bg-surface-2 p-3 text-[11px] leading-relaxed text-content-muted">
        {JSON.stringify(item.raw, null, 2)}
      </pre>
    </details>
  );
}

// ---------------------------------------------------------------------------
// SwipeDetailPanel
// ---------------------------------------------------------------------------

/**
 * Slide-over panel showing full swipe detail: media, ad copy, performance,
 * source dates, analysis metadata, landing page, and raw payload.
 *
 * Follows the same Dialog pattern as AdDetailPanel.
 */
export function SwipeDetailPanel({
  item,
  open,
  onClose,
  onApprove,
  onReject,
  onMarkPending,
}: {
  item: AssetReviewItem | null;
  open: boolean;
  onClose: () => void;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  onMarkPending?: (id: string) => void;
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
                      {item.brandName}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2">
                      <Badge tone={reviewTone(item.reviewStatus)}>
                        {reviewLabel(item.reviewStatus)}
                      </Badge>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {onApprove && item.reviewStatus !== "approved" ? (
                      <Button variant="secondary" size="xs" onClick={() => onApprove(item.id)}>
                        Approve
                      </Button>
                    ) : null}
                    {onReject && item.reviewStatus !== "rejected" ? (
                      <Button variant="secondary" size="xs" onClick={() => onReject(item.id)}>
                        Reject
                      </Button>
                    ) : null}
                    {onMarkPending && item.reviewStatus !== "pending_review" ? (
                      <Button variant="ghost" size="xs" onClick={() => onMarkPending(item.id)}>
                        Mark pending
                      </Button>
                    ) : null}
                    <Dialog.Close render={<Button variant="ghost" size="xs">Close</Button>} />
                  </div>
                </div>

                {/* Scrollable body */}
                <div className="flex-1 overflow-y-auto">
                  <div className="space-y-6 p-6">
                    {/* Media */}
                    {item.media.length > 0 ? (
                      <div className="overflow-hidden rounded-xl border border-border bg-surface-2">
                        <SwipeMedia media={item.media} aspect="4/5" />
                      </div>
                    ) : null}

                    {/* Ad copy */}
                    <AdCopySection item={item} />

                    {/* Performance */}
                    <PerformanceSection item={item} />

                    {/* Source dates */}
                    <SourceDatesSection item={item} />

                    {/* Analysis */}
                    <AnalysisSection item={item} />

                    {/* Landing page */}
                    <LandingPageSection item={item} />

                    {/* Raw payload */}
                    <RawPayloadSection item={item} />
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
