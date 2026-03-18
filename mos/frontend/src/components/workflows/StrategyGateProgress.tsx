import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { StrategyV2PendingSignal } from "./StrategyV2ReviewWorkspace";

export type GateStatus = "completed" | "current" | "upcoming";

const GATE_LABELS: Record<StrategyV2PendingSignal, string> = {
  strategy_v2_proceed_research: "Proceed Research",
  strategy_v2_confirm_competitor_assets: "Confirm Competitor Assets",
  strategy_v2_select_angle: "Select Angle",
  strategy_v2_select_ump_ums: "Select UMP / UMS",
  strategy_v2_select_offer_winner: "Select Offer Winner",
  strategy_v2_approve_final_copy: "Approve Final Copy",
};

const GATE_SEQUENCE: StrategyV2PendingSignal[] = [
  "strategy_v2_proceed_research",
  "strategy_v2_confirm_competitor_assets",
  "strategy_v2_select_angle",
  "strategy_v2_select_ump_ums",
  "strategy_v2_select_offer_winner",
  "strategy_v2_approve_final_copy",
];

const statusTone: Record<GateStatus, "success" | "accent" | "neutral"> = {
  completed: "success",
  current: "accent",
  upcoming: "neutral",
};

const statusLabel: Record<GateStatus, string> = {
  completed: "Completed",
  current: "Current",
  upcoming: "Upcoming",
};

/**
 * Sidebar showing the 6 Strategy V2 gate steps with their completion status.
 * Clicking a completed gate shows its receipt; clicking current clears selection.
 */
export function StrategyGateProgress({
  completedGateCount,
  pendingGateIndex,
  selectedCompletedGate,
  showAllArtifacts,
  onGateClick,
  onToggleArtifacts,
}: {
  completedGateCount: number;
  pendingGateIndex: number;
  selectedCompletedGate: StrategyV2PendingSignal | null;
  showAllArtifacts: boolean;
  onGateClick: (gate: StrategyV2PendingSignal, status: GateStatus) => void;
  onToggleArtifacts: () => void;
}) {
  return (
    <div className="space-y-2">
      {GATE_SEQUENCE.map((gate, index) => {
        const status: GateStatus =
          index < completedGateCount ? "completed" : index === pendingGateIndex ? "current" : "upcoming";
        const isSelected = gate === selectedCompletedGate;
        return (
          <button
            key={gate}
            type="button"
            className={cn(
              "ds-card ds-card--sm w-full text-left",
              status === "upcoming" ? "bg-surface-2 opacity-70 cursor-default" : "bg-surface-2 hover:bg-hover",
              isSelected ? "ring-1 ring-accent" : "",
            )}
            onClick={() => {
              if (status !== "upcoming") onGateClick(gate, status);
            }}
            disabled={status === "upcoming"}
          >
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-xs font-semibold text-content">Step {index + 1}</div>
                <div className="text-xs text-content-muted">{GATE_LABELS[gate]}</div>
              </div>
              <Badge tone={statusTone[status]}>{statusLabel[status]}</Badge>
            </div>
          </button>
        );
      })}

      <Button
        variant="secondary"
        size="xs"
        className="w-full"
        onClick={onToggleArtifacts}
      >
        {showAllArtifacts ? "Hide all artifacts" : "All artifacts"}
      </Button>
    </div>
  );
}
