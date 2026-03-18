import { Badge } from "@/components/ui/badge";
import { useMetaPublishContext, shortId, type MetaWorkflowPhase } from "./MetaPublishProvider";
import { MetaStatsBar } from "./MetaStatsBar";
import { MetaWorkflowStepper } from "./MetaWorkflowStepper";
import { MetaBlockerBanner } from "./MetaBlockerBanner";

export function MetaWorkflowHeader({
  activePhase,
  onPhaseChange,
}: {
  activePhase: MetaWorkflowPhase;
  onPhaseChange: (phase: MetaWorkflowPhase) => void;
}) {
  const { config, configError } = useMetaPublishContext();

  return (
    <div className="space-y-3 border border-border bg-transparent p-4">
      {/* Title row */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-base font-semibold text-content">Meta ads review</div>
          <div className="text-sm text-content-muted">
            Review internal Meta specs, exclude unwanted creatives, validate the final package, publish paused to Meta,
            and monitor post-launch benchmarks.
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-content-muted">
          {config ? (
            <>
              <Badge tone="neutral">Ad account {shortId(config.adAccountId, 4)}</Badge>
              {config.pageId ? <Badge tone="neutral">Page {shortId(config.pageId, 4)}</Badge> : null}
              {config.graphApiVersion ? <Badge tone="neutral">{config.graphApiVersion}</Badge> : null}
            </>
          ) : configError ? (
            <span className="text-danger">{configError}</span>
          ) : (
            <span>Loading Meta config…</span>
          )}
        </div>
      </div>

      {/* Stats pills */}
      <MetaStatsBar />

      {/* Workflow stepper */}
      <MetaWorkflowStepper activePhase={activePhase} onPhaseChange={onPhaseChange} />

      {/* Blockers / warnings */}
      <MetaBlockerBanner />
    </div>
  );
}
