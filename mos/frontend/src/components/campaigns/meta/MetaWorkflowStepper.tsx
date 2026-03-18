import { cn } from "@/lib/utils";
import { useMetaPublishContext, type MetaWorkflowPhase } from "./MetaPublishProvider";

type StepDef = {
  phase: MetaWorkflowPhase;
  label: string;
};

const STEPS: StepDef[] = [
  { phase: "generate", label: "Generate" },
  { phase: "review", label: "Review" },
  { phase: "qa", label: "QA" },
  { phase: "publish", label: "Publish" },
  { phase: "manage", label: "Manage" },
];

type PhaseStatus = "completed" | "active" | "upcoming";

function resolveStepStatus(
  step: MetaWorkflowPhase,
  activePhase: MetaWorkflowPhase,
  context: {
    hasGeneratedAssets: boolean;
    creativeSpecCount: number;
    includedCount: number;
    publishedCount: number;
  },
): PhaseStatus {
  if (step === activePhase) return "active";

  // Simple heuristic for completion
  if (step === "generate" && context.hasGeneratedAssets && context.creativeSpecCount > 0) return "completed";
  if (step === "review" && context.includedCount > 0 && activePhase !== "generate" && activePhase !== "review") return "completed";
  if (step === "publish" && context.publishedCount > 0 && activePhase === "manage") return "completed";

  const stepIndex = STEPS.findIndex((s) => s.phase === step);
  const activeIndex = STEPS.findIndex((s) => s.phase === activePhase);
  if (stepIndex < activeIndex) return "completed";
  return "upcoming";
}

const statusDot: Record<PhaseStatus, string> = {
  completed: "bg-success text-white",
  active: "bg-accent text-white",
  upcoming: "bg-surface-2 text-content-muted",
};

const statusIcon: Record<PhaseStatus, string> = {
  completed: "\u2713",
  active: "\u2022",
  upcoming: "",
};

const statusPill: Record<PhaseStatus, string> = {
  completed: "bg-success/10 text-success",
  active: "bg-accent/10 text-accent",
  upcoming: "bg-surface-2 text-content-muted",
};

const connectorStatus: Record<PhaseStatus, string> = {
  completed: "bg-success",
  active: "bg-accent",
  upcoming: "bg-border",
};

export function MetaWorkflowStepper({
  activePhase,
  onPhaseChange,
}: {
  activePhase: MetaWorkflowPhase;
  onPhaseChange: (phase: MetaWorkflowPhase) => void;
}) {
  const { hasGeneratedAssets, creativeSpecCount, includedPackageItems, visiblePublishRuns } = useMetaPublishContext();

  return (
    <div className="flex items-center gap-0">
      {STEPS.map((step, idx) => {
        const status = resolveStepStatus(step.phase, activePhase, {
          hasGeneratedAssets,
          creativeSpecCount,
          includedCount: includedPackageItems.length,
          publishedCount: visiblePublishRuns.length,
        });
        const prevStatus = idx > 0
          ? resolveStepStatus(STEPS[idx - 1].phase, activePhase, {
              hasGeneratedAssets,
              creativeSpecCount,
              includedCount: includedPackageItems.length,
              publishedCount: visiblePublishRuns.length,
            })
          : null;

        return (
          <div key={step.phase} className="flex items-center">
            {idx > 0 && prevStatus ? (
              <div className={cn("h-0.5 w-6", connectorStatus[prevStatus === "completed" ? "completed" : "upcoming"])} />
            ) : null}
            <button
              type="button"
              onClick={() => onPhaseChange(step.phase)}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition",
                "hover:ring-2 hover:ring-accent/20",
                statusPill[status],
              )}
            >
              <span className={cn("inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold", statusDot[status])}>
                {statusIcon[status]}
              </span>
              {step.label}
            </button>
          </div>
        );
      })}
    </div>
  );
}
