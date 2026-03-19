import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { StrategyV2PendingSignal } from "./StrategyV2ReviewWorkspace";

export type GateStatus = "completed" | "current" | "upcoming";

export const GATE_LABELS: Record<StrategyV2PendingSignal, string> = {
  strategy_v2_proceed_research: "Review Research",
  strategy_v2_confirm_competitor_assets: "Select Competitors",
  strategy_v2_select_angle: "Choose Angle",
  strategy_v2_select_ump_ums: "Choose Messaging",
  strategy_v2_select_offer_winner: "Select Offer",
  strategy_v2_approve_final_copy: "Approve Copy",
};

export const GATE_DESCRIPTIONS: Record<StrategyV2PendingSignal, string> = {
  strategy_v2_proceed_research: "Review foundational market research",
  strategy_v2_confirm_competitor_assets: "Pick competitor reference assets",
  strategy_v2_select_angle: "Pick your marketing angle",
  strategy_v2_select_ump_ums: "Select your messaging proposition pair",
  strategy_v2_select_offer_winner: "Pick the winning offer variant",
  strategy_v2_approve_final_copy: "Review and approve final ad copy",
};

export const GATE_EXPLANATIONS: Record<StrategyV2PendingSignal, string> = {
  strategy_v2_proceed_research:
    "Review the foundational research to confirm the market analysis is solid, then decide whether to proceed.",
  strategy_v2_confirm_competitor_assets:
    "Select 3\u201315 competitor assets the system should reference for your strategy.",
  strategy_v2_select_angle:
    "We generated several marketing angles. Pick the one that best fits your brand.",
  strategy_v2_select_ump_ums:
    "Choose the messaging proposition pair that resonates most with your audience.",
  strategy_v2_select_offer_winner:
    "Review offer variants and pick the winner based on value, risk, and novelty.",
  strategy_v2_approve_final_copy:
    "Read through the final headline, body, presell, and sales page. Approve if ready.",
};

export const GATE_SEQUENCE: StrategyV2PendingSignal[] = [
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
  onGateClick,
}: {
  completedGateCount: number;
  pendingGateIndex: number;
  selectedCompletedGate: StrategyV2PendingSignal | null;
  onGateClick: (gate: StrategyV2PendingSignal, status: GateStatus) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-content px-1">
        Gate {Math.min(completedGateCount + 1, 6)} of 6
      </div>
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
              <div className="min-w-0">
                <div className="text-xs font-semibold text-content">Step {index + 1}: {GATE_LABELS[gate]}</div>
                <div className="text-[11px] text-content-muted truncate">{GATE_DESCRIPTIONS[gate]}</div>
              </div>
              <Badge tone={statusTone[status]}>{statusLabel[status]}</Badge>
            </div>
          </button>
        );
      })}
    </div>
  );
}
