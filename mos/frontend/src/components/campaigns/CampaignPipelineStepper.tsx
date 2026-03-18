import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import type { PipelinePhaseInfo, PhaseStatus } from "@/hooks/useCampaignPipeline";

function StepDot({ status }: { status: PhaseStatus }) {
  if (status === "completed") {
    return (
      <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-success text-white">
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden>
          <path d="M2 5.5L4 7.5L8 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  }
  if (status === "in_progress") {
    return (
      <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent">
        <span className="h-1.5 w-1.5 rounded-full bg-surface" />
      </span>
    );
  }
  return (
    <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border bg-transparent" />
  );
}

/**
 * Horizontal pipeline stepper showing campaign phase progression.
 * Each step is clickable and navigates to the corresponding sub-route.
 */
export function CampaignPipelineStepper({
  phases,
  campaignId,
}: {
  phases: PipelinePhaseInfo[];
  campaignId: string;
}) {
  const navigate = useNavigate();

  return (
    <div className="flex items-center">
      {phases.map((phase, idx) => (
        <div key={phase.phase} className="flex items-center">
          {/* Connector line */}
          {idx > 0 ? (
            <div
              className={cn(
                "h-0.5 w-6",
                phases[idx - 1].status === "completed"
                  ? "bg-success"
                  : "bg-border",
              )}
            />
          ) : null}

          {/* Step */}
          <button
            type="button"
            onClick={() => navigate(`/campaigns/${campaignId}/${phase.route}`)}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition",
              "hover:ring-2 hover:ring-accent/20",
              phase.status === "completed"
                ? "text-success"
                : phase.status === "in_progress"
                  ? "text-accent"
                  : "text-content-muted opacity-50",
            )}
          >
            <StepDot status={phase.status} />
            {phase.label}
          </button>
        </div>
      ))}
    </div>
  );
}
