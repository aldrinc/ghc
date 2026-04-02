import { CheckCircle2, Circle, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export type PhaseStatus = "completed" | "current" | "upcoming" | "blocked";

export type PhaseDefinition = {
  id: string;
  label: string;
  status: PhaseStatus;
  summary?: string;
};

type StrategyProgressSidebarProps = {
  phases: PhaseDefinition[];
  activePhaseId: string;
  onPhaseClick: (id: string) => void;
  approvedBundleId?: string | null;
  selectedAngle?: string | null;
  selectedHeadline?: string | null;
};

const statusIcon: Record<PhaseStatus, React.ReactNode> = {
  completed: <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />,
  current: <Loader2 className="h-4 w-4 shrink-0 animate-spin text-accent" />,
  upcoming: <Circle className="h-4 w-4 shrink-0 text-content-muted" />,
  blocked: <Circle className="h-4 w-4 shrink-0 text-danger" />,
};

const statusTone: Record<PhaseStatus, "success" | "accent" | "neutral" | "danger"> = {
  completed: "success",
  current: "accent",
  upcoming: "neutral",
  blocked: "danger",
};

export function StrategyProgressSidebar({
  phases,
  activePhaseId,
  onPhaseClick,
  approvedBundleId,
  selectedAngle,
  selectedHeadline,
}: StrategyProgressSidebarProps) {
  return (
    <div className="sticky top-4 space-y-1">
      <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-muted">
        Workflow progress
      </div>

      {phases.map((phase, index) => {
        const isActive = phase.id === activePhaseId;
        return (
          <button
            key={phase.id}
            type="button"
            onClick={() => onPhaseClick(phase.id)}
            className={`flex w-full items-start gap-2 rounded-md px-2 py-2 text-left transition-colors ${
              isActive
                ? "bg-accent/10 ring-1 ring-accent/20"
                : "hover:bg-surface-2"
            }`}
          >
            <div className="mt-0.5">{statusIcon[phase.status]}</div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-content-muted">{index + 1}</span>
                <span className={`text-sm font-medium ${isActive ? "text-content" : "text-content-muted"}`}>
                  {phase.label}
                </span>
              </div>
              {phase.summary ? (
                <div className="mt-0.5 truncate text-xs text-content-muted">{phase.summary}</div>
              ) : null}
            </div>
            <Badge tone={statusTone[phase.status]} className="shrink-0 text-[10px]">
              {phase.status === "completed"
                ? "Done"
                : phase.status === "current"
                  ? "Active"
                  : phase.status === "blocked"
                    ? "Blocked"
                    : ""}
            </Badge>
          </button>
        );
      })}

      {approvedBundleId || selectedAngle || selectedHeadline ? (
        <div className="mt-4 space-y-2 border-t border-border pt-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">Live state</div>
          {approvedBundleId ? (
            <div className="text-xs text-content-muted">
              <span className="font-medium text-content">Bundle</span>{" "}
              <span className="font-mono">{approvedBundleId.slice(0, 8)}...</span>
            </div>
          ) : null}
          {selectedAngle ? (
            <div className="text-xs text-content-muted">
              <span className="font-medium text-content">Angle</span> {selectedAngle}
            </div>
          ) : null}
          {selectedHeadline ? (
            <div className="truncate text-xs text-content-muted">
              <span className="font-medium text-content">Headline</span> {selectedHeadline}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
