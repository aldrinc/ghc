import { useCallback, useMemo, useState } from "react";
import { useLatestArtifact } from "@/api/artifacts";
import { useAdsApi } from "@/api/ads";
import { Callout } from "@/components/ui/callout";
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

  const showRetry = Boolean(
    visible &&
      clientId &&
      productId &&
      (ingestionStatus === "failed" || ingestionStatus === "partial"),
  );
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

  const subtitle = !canRetry
    ? [ "Missing ads research run id; cannot retry from UI.", ingestionError || ingestionReason ]
        .filter(Boolean)
        .join(" ")
    : ingestionError || ingestionReason;

  return (
    <Callout
      variant="warning"
      size="sm"
      title={ingestionStatus === "partial" ? "Ads ingestion partially failed during onboarding" : "Ads ingestion failed during onboarding"}
      actions={
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={handleRetry}
          disabled={retrying || !canRetry}
        >
          {retrying ? "Retrying..." : "Retry ingestion"}
        </Button>
      }
    >
      {subtitle}
    </Callout>
  );
}
