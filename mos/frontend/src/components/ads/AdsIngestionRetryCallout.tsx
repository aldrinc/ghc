import { useCallback, useMemo, useState } from "react";
import { useLatestArtifact } from "@/api/artifacts";
import { useAdsApi } from "@/api/ads";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";

type AdsIngestionRetryCalloutProps = {
  clientId?: string;
  productId?: string;
  visible?: boolean;
};

export function AdsIngestionRetryCallout({
  clientId,
  productId,
  visible = true,
}: AdsIngestionRetryCalloutProps) {
  const { retryIngestion } = useAdsApi();
  const { latest: canonArtifact } = useLatestArtifact({
    clientId,
    productId,
    type: "client_canon",
  });
  const [retrying, setRetrying] = useState(false);

  const research = useMemo(() => {
    const data: any = canonArtifact?.data;
    const precanon = data?.precanon_research || data?.precanonResearch;
    if (!precanon || typeof precanon !== "object") return null;
    return precanon as Record<string, unknown>;
  }, [canonArtifact?.data]);

  const ingestionStatus =
    (research as any)?.ads_ingestion_status || (research as any)?.adsIngestionStatus || null;
  const ingestionError =
    (research as any)?.ads_ingestion_error || (research as any)?.adsIngestionError || null;
  const ingestionReason =
    (research as any)?.ads_ingestion_reason || (research as any)?.adsIngestionReason || null;
  const adsResearchRunId =
    (research as any)?.ads_research_run_id || (research as any)?.adsResearchRunId || null;

  const showRetry = Boolean(visible && clientId && productId && ingestionStatus === "failed");
  const canRetry = Boolean(adsResearchRunId);

  const handleRetry = useCallback(async () => {
    if (!adsResearchRunId) {
      toast.error("Cannot retry ads ingestion: missing ads research run id.");
      return;
    }
    setRetrying(true);
    try {
      const resp = await retryIngestion({
        researchRunId: String(adsResearchRunId),
        runCreativeAnalysis: true,
      });
      toast.success({
        title: "Ads ingestion retry started",
        description: resp?.temporal_workflow_id ? `Workflow: ${resp.temporal_workflow_id}` : undefined,
      });
    } catch (err: any) {
      toast.error(err?.message || "Failed to start ads ingestion retry");
    } finally {
      setRetrying(false);
    }
  }, [adsResearchRunId, retryIngestion]);

  if (!showRetry) return null;

  const subtitle = !canRetry ? "Missing ads research run id; cannot retry from UI." : ingestionError || ingestionReason;

  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="font-semibold">Ads ingestion failed during onboarding</div>
          {subtitle ? <div className="mt-0.5 truncate text-xs text-amber-900/80">{subtitle}</div> : null}
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={handleRetry}
          disabled={retrying || !canRetry}
        >
          {retrying ? "Retrying..." : "Retry ingestion"}
        </Button>
      </div>
    </div>
  );
}
