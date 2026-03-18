import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useCampaignContext } from "@/contexts/CampaignContext";
import { getAdapter } from "@/providers/adPlatformRegistry";
import type { AdPlatformId } from "@/types/adPlatform";

/**
 * Generic shell that renders the platform-specific publish workspace
 * by looking up the adapter from the registry.
 */
export function PlatformPublishWorkspace() {
  const navigate = useNavigate();
  const { platformId } = useParams<{ platformId: string }>();
  const { campaignId } = useCampaignContext();

  const adapter = platformId ? getAdapter(platformId as AdPlatformId) : undefined;

  if (!adapter) {
    return (
      <div className="space-y-4">
        <div className="border border-border bg-transparent px-4 py-3 text-base text-danger">
          Platform "{platformId}" is not available or not registered.
        </div>
        <Button variant="secondary" size="sm" onClick={() => navigate(`/campaigns/${campaignId}/publish`)}>
          Back to platforms
        </Button>
      </div>
    );
  }

  const { PublishPanel } = adapter;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="xs"
          onClick={() => navigate(`/campaigns/${campaignId}/publish`)}
        >
          &larr; All platforms
        </Button>
        <div className="text-base font-semibold text-content">{adapter.label}</div>
      </div>
      <PublishPanel campaignId={campaignId} />
    </div>
  );
}
