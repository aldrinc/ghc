import { useMemo } from "react";
import { useWorkflows, useWorkflowDetail } from "@/api/workflows";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";

export type JourneyPhase =
  | { phase: "no-workspace" }
  | { phase: "onboarding-running" }
  | { phase: "strategy-processing"; stage?: string }
  | { phase: "strategy-needs-input"; gateIndex: number; workflowId: string }
  | { phase: "strategy-complete"; workflowId: string }
  | { phase: "campaigns-active"; count: number }
  | { phase: "idle" };

export function useJourneyPhase(): JourneyPhase {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { data: workflows = [] } = useWorkflows();

  const workspaceWorkflows = useMemo(
    () =>
      workflows
        .filter((wf) => wf.client_id === workspace?.id && (!product?.id || wf.product_id === product.id))
        .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()),
    [workflows, workspace?.id, product?.id],
  );

  const latestWorkflow = workspaceWorkflows[0];
  const { data: workflowDetail } = useWorkflowDetail(latestWorkflow?.id);
  const latestRun = workflowDetail?.run ?? latestWorkflow;

  return useMemo(() => {
    if (!workspace?.id) return { phase: "no-workspace" };
    if (!latestRun) return { phase: "idle" };

    if (latestRun.kind === "client_onboarding" && latestRun.status === "running") {
      return { phase: "onboarding-running" };
    }

    if (latestRun.kind === "strategy_v2") {
      const state = workflowDetail?.strategy_v2_state;
      const pending = state?.pending_signal_type || state?.required_signal_type;
      const launches = workflowDetail?.strategy_v2_launches;

      if (latestRun.status === "running") {
        if (pending) {
          const GATE_SIGNALS = [
            "strategy_v2_proceed_research",
            "strategy_v2_confirm_competitor_assets",
            "strategy_v2_select_angle",
            "strategy_v2_select_ump_ums",
            "strategy_v2_select_offer_winner",
            "strategy_v2_approve_final_copy",
          ];
          const gateIndex = GATE_SIGNALS.indexOf(pending as string);
          return { phase: "strategy-needs-input", gateIndex: gateIndex >= 0 ? gateIndex : 0, workflowId: latestRun.id };
        }
        return { phase: "strategy-processing", stage: state?.current_stage || undefined };
      }

      if (latestRun.status === "completed") {
        if (Array.isArray(launches) && launches.length > 0) {
          return { phase: "campaigns-active", count: launches.length };
        }
        return { phase: "strategy-complete", workflowId: latestRun.id };
      }
    }

    // Check if there are any campaigns by looking at strategy_v2 workflows
    const strategyRuns = workspaceWorkflows.filter((wf) => wf.kind === "strategy_v2");
    // We can't easily check launches without detail, so fall through
    void strategyRuns;

    return { phase: "idle" };
  }, [workspace?.id, latestRun, workflowDetail, workspaceWorkflows]);
}
