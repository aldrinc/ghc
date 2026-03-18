import { useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCampaignContext } from "@/contexts/CampaignContext";
import { getAllAdapters } from "@/providers/adPlatformRegistry";
import { AD_PLATFORM_DEFINITIONS, type AdPlatformId } from "@/types/adPlatform";

/**
 * Platform overview page for the Publish tab.
 * Shows configured ad platforms as cards with status and links to their workspaces.
 */
export function CampaignPublishTab() {
  const navigate = useNavigate();
  const { campaignId } = useCampaignContext();
  const adapters = getAllAdapters();

  // Platforms that have a registered adapter
  const registeredIds = new Set(adapters.map((a) => a.id));

  // All known platforms from definitions
  const allPlatforms = Object.values(AD_PLATFORM_DEFINITIONS);

  return (
    <div className="space-y-6">
      <div>
        <div className="text-base font-semibold text-content">Ad platforms</div>
        <div className="text-sm text-content-muted">
          Configure and publish ads to each platform. Click a platform to open its publish workspace.
        </div>
      </div>

      {/* Available platforms — full cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {allPlatforms.filter((p) => registeredIds.has(p.id)).map((platform) => (
          <div
            key={platform.id}
            className="flex flex-col justify-between rounded-lg border border-border bg-surface p-4"
          >
            <div>
              <div className="flex items-center gap-2">
                <div className="text-sm font-semibold text-content">{platform.label}</div>
                <Badge tone="success">Available</Badge>
              </div>
              <div className="mt-1 text-xs text-content-muted">
                Formats: {platform.supportedCreativeFormats.join(", ")}
              </div>
            </div>
            <div className="mt-4">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate(`/campaigns/${campaignId}/publish/${platform.id}`)}
              >
                Open workspace
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Upcoming platforms — compact list */}
      {allPlatforms.some((p) => !registeredIds.has(p.id)) ? (
        <div className="mt-2 text-xs text-content-muted">
          <span className="font-medium">Coming soon:</span>{" "}
          {allPlatforms
            .filter((p) => !registeredIds.has(p.id))
            .map((p) => p.label)
            .join(", ")}
        </div>
      ) : null}
    </div>
  );
}
