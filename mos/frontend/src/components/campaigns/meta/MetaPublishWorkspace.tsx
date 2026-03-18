import { useState } from "react";
import type { AssetBrief } from "@/types/artifacts";
import type { Campaign } from "@/types/common";
import { MetaPublishProvider, type MetaWorkflowPhase } from "./MetaPublishProvider";
import { MetaWorkflowHeader } from "./MetaWorkflowHeader";
import { MetaFunnelScopeBar } from "./MetaFunnelScopeBar";
import { MetaGeneratePanel } from "./MetaGeneratePanel";
import { MetaReviewPanel } from "./MetaReviewPanel";
import { MetaQaPanel } from "./MetaQaPanel";
import { MetaPublishConfigPanel } from "./MetaPublishConfigPanel";
import { MetaManagementPanel } from "./MetaManagementPanel";

function MetaPublishWorkspaceInner() {
  const [activePhase, setActivePhase] = useState<MetaWorkflowPhase>("review");

  return (
    <div className="space-y-4">
      <MetaWorkflowHeader activePhase={activePhase} onPhaseChange={setActivePhase} />
      <MetaFunnelScopeBar />

      {activePhase === "generate" ? <MetaGeneratePanel /> : null}
      {activePhase === "review" ? <MetaReviewPanel onAdvance={() => setActivePhase("qa")} /> : null}
      {activePhase === "qa" ? <MetaQaPanel onAdvance={() => setActivePhase("publish")} /> : null}
      {activePhase === "publish" ? <MetaPublishConfigPanel /> : null}
      {activePhase === "manage" ? <MetaManagementPanel /> : null}
    </div>
  );
}

/**
 * Top-level Meta ads workspace. Wraps everything in the MetaPublishProvider
 * context and renders the stepper-driven layout.
 *
 * Drop-in replacement for the old CampaignMetaAdsPanel.
 */
export function MetaPublishWorkspace({
  campaign,
  assetBriefs,
}: {
  campaign: Campaign;
  assetBriefs: AssetBrief[];
}) {
  return (
    <MetaPublishProvider campaign={campaign} assetBriefs={assetBriefs}>
      <MetaPublishWorkspaceInner />
    </MetaPublishProvider>
  );
}
