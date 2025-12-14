import { useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";

export function CampaignDetailPage() {
  const { campaignId } = useParams();
  return (
    <div className="space-y-4">
      <PageHeader title="Campaign detail" description="Planning status, workflows, and next steps." />
      <div className="rounded-lg border border-border bg-white p-4 text-sm text-content shadow-sm">
        Campaign detail coming soon. Campaign ID:{" "}
        <span className="font-mono text-xs text-content-muted">{campaignId}</span>
      </div>
    </div>
  );
}
