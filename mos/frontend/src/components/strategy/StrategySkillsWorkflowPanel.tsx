import { useMemo, useCallback } from "react";

import {
  useActivateStrategyHandoff,
  useApproveFoundationalStrategySkills,
  useApproveStrategyRole,
  useBootstrapStrategySkills,
  useRunStrategySkillsStage,
  useSelectStrategyAngle,
  useSelectStrategyHeadline,
  useStrategySkillsStatus,
  type StrategySkillsBundle,
  type StrategySkillsBundleItem,
} from "@/api/productStrategySkills";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";

import { StrategyProgressSidebar, type PhaseDefinition, type PhaseStatus } from "./StrategyProgressSidebar";
import { ActivationStep } from "./steps/ActivationStep";
import { AngleSelectionStep } from "./steps/AngleSelectionStep";
import { BootstrapStep } from "./steps/BootstrapStep";
import { FoundationalStep } from "./steps/FoundationalStep";
import { HeadlineSelectionStep } from "./steps/HeadlineSelectionStep";
import { StageStep, type StageDefinition } from "./steps/StageStep";

type StrategySkillsWorkflowPanelProps = {
  productId: string;
  productTitle: string;
};

type SelectionSummary = {
  id: string;
  label: string;
  rationale: string;
};

const STAGE_DEFINITIONS: StageDefinition[] = [
  { key: "signal_report", label: "Signal Report", role: "signal_report", approvalRequired: true },
  { key: "angle_library", label: "Angle Library", role: "angle_library", selectionType: "angle" },
  { key: "knowledge_base", label: "Knowledge Base", role: "knowledge_base", approvalRequired: true },
  { key: "cso", label: "CSO", role: "cso", approvalRequired: true },
  { key: "offer_document", label: "Offer Document", role: "offer_document", approvalRequired: true },
  { key: "headline_pool", label: "Headline Pool", role: "headline_pool", selectionType: "headline" },
  { key: "presell_page", label: "Presell Page", role: "presell_page", approvalRequired: true },
  { key: "sales_page", label: "Sales Page", role: "sales_page", approvalRequired: true },
];

function bundleRoleMap(bundle?: StrategySkillsBundle | null) {
  const map = new Map<string, StrategySkillsBundleItem>();
  for (const item of bundle?.items ?? []) {
    map.set(item.role, item);
  }
  return map;
}

function bundleSelectionSummary(
  bundle: StrategySkillsBundle | null | undefined,
  selectionRole: "angle_selection" | "headline_selection",
): SelectionSummary | null {
  const item = bundleRoleMap(bundle).get(selectionRole);
  const payload = item?.artifactData?.json;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const record = payload as Record<string, unknown>;

  if (selectionRole === "angle_selection") {
    const selectedAngle = record.selectedAngle;
    const angle =
      selectedAngle && typeof selectedAngle === "object" && !Array.isArray(selectedAngle)
        ? (selectedAngle as Record<string, unknown>)
        : null;
    const id = String(record.selectedAngleId ?? "").trim();
    const label = String(angle?.angleName ?? "").trim();
    const rationale = String(record.rationale ?? "").trim();
    if (!id || !label) return null;
    return { id, label, rationale };
  }

  const selectedHeadline = record.selectedHeadline;
  const headline =
    selectedHeadline && typeof selectedHeadline === "object" && !Array.isArray(selectedHeadline)
      ? (selectedHeadline as Record<string, unknown>)
      : null;
  const id = String(record.selectedHeadlineId ?? "").trim();
  const label = String(headline?.headline ?? "").trim();
  const rationale = String(record.rationale ?? "").trim();
  if (!id || !label) return null;
  return { id, label, rationale };
}

function computeActivePhase(
  bootstrapNeeded: boolean,
  foundationalReadyToApprove: boolean,
  workingRoleMap: Map<string, StrategySkillsBundleItem>,
  handoffRoleMap: Map<string, StrategySkillsBundleItem>,
  activeAngleSelection: SelectionSummary | null,
  activeHeadlineSelection: SelectionSummary | null,
  pendingHandoffBundles: StrategySkillsBundle[],
): string {
  if (bootstrapNeeded) return "bootstrap";
  if (foundationalReadyToApprove) return "foundational";

  // Find the first stage that hasn't been approved yet
  for (const stage of STAGE_DEFINITIONS) {
    const workingItem = workingRoleMap.get(stage.role);
    const approvedItem = handoffRoleMap.get(stage.role);

    if (!approvedItem && !workingItem) {
      return `stage-${stage.key}`;
    }

    if (stage.selectionType === "angle" && !activeAngleSelection && approvedItem) {
      return "angle-selection";
    }
    if (stage.selectionType === "headline" && !activeHeadlineSelection && approvedItem) {
      return "headline-selection";
    }

    if (stage.approvalRequired && workingItem && workingItem.artifactId !== approvedItem?.artifactId) {
      return `stage-${stage.key}`;
    }
  }

  if (pendingHandoffBundles.length) return "activation";

  return "activation";
}

export function StrategySkillsWorkflowPanel({
  productId,
  productTitle,
}: StrategySkillsWorkflowPanelProps) {
  const { data: status, isLoading } = useStrategySkillsStatus(productId);
  const bootstrap = useBootstrapStrategySkills(productId);
  const approveFoundational = useApproveFoundationalStrategySkills(productId);
  const runStage = useRunStrategySkillsStage(productId);
  const selectAngle = useSelectStrategyAngle(productId);
  const selectHeadline = useSelectStrategyHeadline(productId);
  const approveRole = useApproveStrategyRole(productId);
  const activateHandoff = useActivateStrategyHandoff(productId);

  const workingRoleMap = useMemo(
    () => bundleRoleMap(status?.activeWorkingBundle),
    [status?.activeWorkingBundle],
  );
  const handoffRoleMap = useMemo(
    () => bundleRoleMap(status?.activeHandoffBundle),
    [status?.activeHandoffBundle],
  );

  const activeAngleSelection = useMemo(
    () => bundleSelectionSummary(status?.activeHandoffBundle, "angle_selection"),
    [status?.activeHandoffBundle],
  );
  const activeHeadlineSelection = useMemo(
    () => bundleSelectionSummary(status?.activeHandoffBundle, "headline_selection"),
    [status?.activeHandoffBundle],
  );

  const pendingHandoffBundles = status?.pendingHandoffBundles ?? [];
  const historicalHandoffBundles = status?.historicalHandoffBundles ?? [];

  const bootstrapNeeded = !status?.skillsBinding || !status?.activeFoundationalBundle;
  const foundationalReadyToApprove = Boolean(
    status?.activeFoundationalBundle && !status?.activeWorkingBundle && !status?.activeHandoffBundle,
  );
  const legacyFoundationalMetadataMissing = Boolean(
    status?.activeFoundationalBundle &&
      status?.foundationalCompleteness &&
      status.foundationalCompleteness.expectedDocKeys.length === 0 &&
      status.foundationalCompleteness.presentDocKeys.length === 0 &&
      status.foundationalCompleteness.missingDocKeys.length === 0 &&
      status.activeFoundationalBundle.items.length > 0,
  );

  const activePhaseId = useMemo(
    () =>
      computeActivePhase(
        bootstrapNeeded,
        foundationalReadyToApprove,
        workingRoleMap,
        handoffRoleMap,
        activeAngleSelection,
        activeHeadlineSelection,
        pendingHandoffBundles,
      ),
    [
      bootstrapNeeded,
      foundationalReadyToApprove,
      workingRoleMap,
      handoffRoleMap,
      activeAngleSelection,
      activeHeadlineSelection,
      pendingHandoffBundles,
    ],
  );

  const phases = useMemo((): PhaseDefinition[] => {
    const result: PhaseDefinition[] = [];

    // Phase 1: Bootstrap
    const bootstrapCompleted = !bootstrapNeeded;
    result.push({
      id: "bootstrap",
      label: "Bootstrap",
      status: bootstrapNeeded
        ? activePhaseId === "bootstrap"
          ? "current"
          : "blocked"
        : "completed",
      summary: bootstrapCompleted ? "Skills bound" : undefined,
    });

    // Phase 2: Foundational
    const foundationalCompleted = bootstrapCompleted && !foundationalReadyToApprove;
    result.push({
      id: "foundational",
      label: "Foundational",
      status: !bootstrapCompleted
        ? "upcoming"
        : foundationalReadyToApprove
          ? "current"
          : foundationalCompleted
            ? "completed"
            : "upcoming",
      summary: foundationalCompleted ? "Approved" : undefined,
    });

    // Phases 3-10: The 8 stages
    for (const stage of STAGE_DEFINITIONS) {
      const workingItem = workingRoleMap.get(stage.role);
      const approvedItem = handoffRoleMap.get(stage.role);
      const needsApproval =
        Boolean(stage.approvalRequired) &&
        Boolean(workingItem) &&
        workingItem?.artifactId !== approvedItem?.artifactId;

      let phaseStatus: PhaseStatus = "upcoming";
      if (!foundationalCompleted) {
        phaseStatus = "upcoming";
      } else if (approvedItem && !needsApproval) {
        phaseStatus = "completed";
      } else if (activePhaseId === `stage-${stage.key}`) {
        phaseStatus = "current";
      } else if (workingItem) {
        phaseStatus = needsApproval ? "current" : "completed";
      }

      result.push({
        id: `stage-${stage.key}`,
        label: stage.label,
        status: phaseStatus,
        summary: approvedItem && !needsApproval ? "Approved" : workingItem ? "Draft ready" : undefined,
      });
    }

    // Phase: Angle selection
    result.push({
      id: "angle-selection",
      label: "Select Angle",
      status: activeAngleSelection
        ? "completed"
        : activePhaseId === "angle-selection"
          ? "current"
          : !foundationalCompleted
            ? "upcoming"
            : workingRoleMap.has("angle_library")
              ? "upcoming"
              : "upcoming",
      summary: activeAngleSelection?.label,
    });

    // Phase: Headline selection
    result.push({
      id: "headline-selection",
      label: "Select Headline",
      status: activeHeadlineSelection
        ? "completed"
        : activePhaseId === "headline-selection"
          ? "current"
          : "upcoming",
      summary: activeHeadlineSelection?.label,
    });

    // Phase: Activation
    result.push({
      id: "activation",
      label: "Activate",
      status: pendingHandoffBundles.length
        ? "current"
        : status?.activeHandoffBundle
          ? "completed"
          : "upcoming",
      summary: pendingHandoffBundles.length
        ? `${pendingHandoffBundles.length} pending`
        : status?.activeHandoffBundle
          ? "Live"
          : undefined,
    });

    return result;
  }, [
    bootstrapNeeded,
    foundationalReadyToApprove,
    activePhaseId,
    workingRoleMap,
    handoffRoleMap,
    activeAngleSelection,
    activeHeadlineSelection,
    pendingHandoffBundles,
    status?.activeHandoffBundle,
  ]);

  const handlePhaseClick = useCallback((id: string) => {
    const el = document.getElementById(`step-${id.replace("stage-", "stage-")}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  if (isLoading) {
    return (
      <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">
        Loading strategy workflow...
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
      {/* Sidebar */}
      <div className="hidden lg:block">
        <StrategyProgressSidebar
          phases={phases}
          activePhaseId={activePhaseId}
          onPhaseClick={handlePhaseClick}
          approvedBundleId={status?.activeHandoffBundle?.id}
          selectedAngle={activeAngleSelection?.label}
          selectedHeadline={activeHeadlineSelection?.label}
        />
      </div>

      {/* Main content: vertical timeline */}
      <div className="space-y-3">
        {/* Header bar */}
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
          <div className="text-sm font-semibold text-content">Strategy Workflow</div>
          {bootstrapNeeded ? (
            <Badge tone="warning">Bootstrap required</Badge>
          ) : pendingHandoffBundles.length ? (
            <Badge tone="warning">Review ready</Badge>
          ) : status?.activeHandoffBundle ? (
            <Badge tone="success">Active</Badge>
          ) : (
            <Badge tone="neutral">Draft only</Badge>
          )}
          <span className="text-xs text-content-muted">{productTitle}</span>
        </div>

        {/* Guidance callout for pending activations */}
        {pendingHandoffBundles.length ? (
          <Callout variant="warning" title="Reviewed snapshot waiting for activation">
            A newer approved snapshot is ready. Activate it when you want sites and campaigns to use the updated strategy.
          </Callout>
        ) : null}

        {/* Step 1: Bootstrap */}
        <BootstrapStep
          isActive={activePhaseId === "bootstrap"}
          isCompleted={!bootstrapNeeded}
          bootstrap={bootstrap}
        />

        {/* Step 2: Foundational */}
        <FoundationalStep
          isActive={activePhaseId === "foundational"}
          isCompleted={!bootstrapNeeded && !foundationalReadyToApprove}
          completeness={status?.foundationalCompleteness}
          legacyMetadataMissing={legacyFoundationalMetadataMissing}
          approveFoundational={approveFoundational}
        />

        {/* Steps 3-10: The 8 strategy stages */}
        {!bootstrapNeeded && !foundationalReadyToApprove ? (
          <div className="space-y-2">
            <div className="px-1 text-xs font-semibold uppercase tracking-wide text-content-muted">
              Strategy stages
            </div>
            {STAGE_DEFINITIONS.map((stage, index) => {
              const workingItem = workingRoleMap.get(stage.role);
              const approvedItem = handoffRoleMap.get(stage.role);
              const isStageActive = activePhaseId === `stage-${stage.key}`;
              const isUpcoming = !workingItem && !approvedItem;

              return (
                <StageStep
                  key={stage.key}
                  stage={stage}
                  stageIndex={index}
                  isActive={isStageActive}
                  isUpcoming={isUpcoming && !isStageActive}
                  workingItem={workingItem}
                  approvedItem={approvedItem}
                  approvedBundle={status?.activeHandoffBundle}
                  runStage={runStage}
                  approveRole={approveRole}
                />
              );
            })}
          </div>
        ) : null}

        {/* Angle selection */}
        {!bootstrapNeeded && !foundationalReadyToApprove ? (
          <AngleSelectionStep
            isActive={activePhaseId === "angle-selection"}
            isCompleted={Boolean(activeAngleSelection)}
            isUpcoming={!workingRoleMap.has("angle_library") && !handoffRoleMap.has("angle_library")}
            productTitle={productTitle}
            workingAngleLibraryItem={workingRoleMap.get("angle_library")}
            approvedAngleLibraryItem={handoffRoleMap.get("angle_library")}
            activeAngleSelection={activeAngleSelection}
            selectAngle={selectAngle}
          />
        ) : null}

        {/* Headline selection */}
        {!bootstrapNeeded && !foundationalReadyToApprove ? (
          <HeadlineSelectionStep
            isActive={activePhaseId === "headline-selection"}
            isCompleted={Boolean(activeHeadlineSelection)}
            isUpcoming={!workingRoleMap.has("headline_pool") && !handoffRoleMap.has("headline_pool")}
            workingHeadlinePoolItem={workingRoleMap.get("headline_pool")}
            activeHeadlineSelection={activeHeadlineSelection}
            selectHeadline={selectHeadline}
          />
        ) : null}

        {/* Activation */}
        {!bootstrapNeeded && !foundationalReadyToApprove ? (
          <ActivationStep
            isActive={activePhaseId === "activation"}
            isCompleted={Boolean(status?.activeHandoffBundle) && !pendingHandoffBundles.length}
            isUpcoming={!status?.activeHandoffBundle && !pendingHandoffBundles.length}
            pendingHandoffBundles={pendingHandoffBundles}
            historicalHandoffBundles={historicalHandoffBundles}
            activateHandoff={activateHandoff}
          />
        ) : null}
      </div>
    </div>
  );
}
