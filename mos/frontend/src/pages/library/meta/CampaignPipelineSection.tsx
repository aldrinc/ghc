import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/layout/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { MediaTile } from "@/components/library/MediaViewer";
import { formatDate, shortId } from "@/lib/format";
import type { Campaign } from "@/types/common";
import type { MetaPipelineAsset } from "@/types/meta";
import type { MediaAsset } from "@/types/library";

type Experiment = { id: string; name: string };

export type CampaignPipelineSectionProps = {
  hasWorkspace: boolean;
  productSelected: boolean;
  campaigns: Campaign[];
  campaignId: string;
  onCampaignChange: (id: string) => void;
  campaignError: string | null;
  experiments: Experiment[];
  experimentId: string;
  onExperimentChange: (id: string) => void;
  statuses: string[];
  onStatusChange: (statuses: string[]) => void;
  pipeline: MetaPipelineAsset[];
  pipelineLoading: boolean;
  pipelineError: string | null;
};

function stepClass(status?: string | null) {
  if (!status || status === "missing") return "border-border bg-muted text-content-muted";
  if (["draft", "pending"].includes(status)) return "border-warning/30 bg-warning/10 text-warning";
  if (["ready", "uploaded", "approved", "active"].includes(status))
    return "border-success/30 bg-success/10 text-success";
  return "border-border bg-surface-2 text-content";
}

function PipelineStep({ label, status, count }: { label: string; status?: string | null; count?: number }) {
  const resolved = status || "missing";
  return (
    <div className={`rounded-md border px-2 py-1 text-xs font-semibold ${stepClass(resolved)}`}>
      {label}: {resolved}
      {typeof count === "number" ? ` · ${count}` : ""}
    </div>
  );
}

function buildMediaAsset(item: MetaPipelineAsset): MediaAsset | undefined {
  const url = item.asset.public_url;
  if (!url) return undefined;
  const isVideo = item.asset.content_type?.startsWith("video/");
  if (isVideo) {
    return { type: "video", url, posterUrl: url };
  }
  return { type: "image", url, thumbUrl: url, alt: item.asset.asset_kind || "Creative asset" };
}

function PipelineLoadingSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="ds-card ds-card--md shadow-none space-y-3 animate-pulse">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1 flex-1">
              <div className="h-4 w-2/3 rounded bg-surface-2" />
              <div className="h-3 w-1/3 rounded bg-surface-2" />
            </div>
            <div className="h-5 w-16 rounded-full bg-surface-2" />
          </div>
          <div className="h-32 w-full rounded bg-surface-2" />
          <div className="grid grid-cols-2 gap-2">
            <div className="h-7 rounded bg-surface-2" />
            <div className="h-7 rounded bg-surface-2" />
            <div className="h-7 rounded bg-surface-2" />
            <div className="h-7 rounded bg-surface-2" />
          </div>
        </div>
      ))}
    </div>
  );
}

const statusOptions = [
  { label: "Approved", value: "approved" },
  { label: "Draft", value: "draft" },
  { label: "Rejected", value: "rejected" },
  { label: "Pending", value: "pending" },
];

export function CampaignPipelineSection({
  hasWorkspace,
  productSelected,
  campaigns,
  campaignId,
  onCampaignChange,
  campaignError,
  experiments,
  experimentId,
  onExperimentChange,
  statuses,
  onStatusChange,
  pipeline,
  pipelineLoading,
  pipelineError,
}: CampaignPipelineSectionProps) {
  const selectedStatus = statuses[0] || "";

  const campaignOptions = useMemo(() => {
    const options = [{ label: "All campaigns", value: "" }];
    return options.concat(campaigns.map((c) => ({ label: c.name, value: c.id })));
  }, [campaigns]);

  const experimentOptions = useMemo(() => {
    const options = [{ label: "All angles", value: "" }];
    return options.concat(experiments.map((e) => ({ label: e.name, value: e.id })));
  }, [experiments]);

  return (
    <div className="ds-card ds-card--md shadow-none space-y-3">
      <div>
        <div className="text-sm font-semibold text-content">Campaign pipeline</div>
        <div className="text-xs text-content-muted">
          Track how angles and assets become Meta creatives and ads.
        </div>
      </div>

      {!hasWorkspace && (
        <EmptyState description="Select a workspace to view pipeline assets." />
      )}

      {hasWorkspace && !productSelected && (
        <EmptyState description="Select a product to view campaigns and pipeline assets for this workspace." />
      )}

      {hasWorkspace && (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Campaign</label>
            <Select
              value={campaignId}
              onValueChange={onCampaignChange}
              options={campaignOptions}
              disabled={!productSelected}
            />
            {campaignError && <div className="text-xs text-danger">{campaignError}</div>}
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Angle</label>
            <Select
              value={experimentId}
              onValueChange={onExperimentChange}
              options={experimentOptions}
              disabled={!productSelected}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Asset status</label>
            <Select
              value={selectedStatus}
              onValueChange={(value) => onStatusChange(value ? [value] : [])}
              options={[{ label: "All statuses", value: "" }, ...statusOptions]}
            />
          </div>
        </div>
      )}

      {hasWorkspace && pipelineError && (
        <Callout variant="danger" size="sm">
          {pipelineError}
        </Callout>
      )}

      {hasWorkspace && pipelineLoading && <PipelineLoadingSkeleton />}

      {hasWorkspace && productSelected && !pipelineLoading && pipeline.length === 0 && !pipelineError && (
        <EmptyState description="No pipeline assets match this filter." />
      )}

      {hasWorkspace && !pipelineLoading && pipeline.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {pipeline.map((item) => {
            const media = buildMediaAsset(item);
            const creativeCount = item.meta?.creatives?.length || 0;
            const adCount = item.meta?.ads?.length || 0;
            const specStatus = item.creative_spec?.status || (item.creative_spec ? "ready" : "missing");
            const uploadStatus = item.meta?.upload?.status || (item.meta?.upload ? "uploaded" : "missing");
            const creativeStatus = creativeCount > 0 ? "ready" : "missing";
            const adStatus = adCount > 0 ? "ready" : "missing";

            return (
              <div key={item.asset.id} className="ds-card ds-card--md shadow-none space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="text-sm font-semibold text-content">
                      {item.campaign?.name || "Unlinked campaign"}
                    </div>
                    <div className="text-xs text-content-muted">
                      {item.experiment?.name || "No angle linked"}
                    </div>
                  </div>
                  <StatusBadge status={item.asset.status || "unknown"} />
                </div>

                <MediaTile asset={media} />

                <div className="flex flex-wrap items-center gap-2 text-xs text-content-muted">
                  <span>Asset {shortId(item.asset.id, 4)}</span>
                  {item.asset.asset_kind ? <Badge tone="neutral">{item.asset.asset_kind}</Badge> : null}
                  {item.asset.width && item.asset.height ? (
                    <span>
                      {item.asset.width}×{item.asset.height}
                    </span>
                  ) : null}
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <PipelineStep label="Spec" status={specStatus} />
                  <PipelineStep label="Upload" status={uploadStatus} />
                  <PipelineStep label="Creative" status={creativeStatus} count={creativeCount} />
                  <PipelineStep label="Ad" status={adStatus} count={adCount} />
                </div>

                <div className="space-y-1 text-xs text-content-muted">
                  <div>
                    Meta campaign:{" "}
                    {item.meta?.meta_campaign?.meta_campaign_id
                      ? shortId(item.meta.meta_campaign.meta_campaign_id, 4)
                      : "—"}
                  </div>
                  <div>Created: {formatDate(item.asset.created_at)}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
