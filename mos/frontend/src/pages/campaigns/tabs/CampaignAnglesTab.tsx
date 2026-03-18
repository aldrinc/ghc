import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useApiClient, type ApiError } from "@/api/client";
import { useUpdateExperimentSpecs } from "@/api/campaigns";
import { useWorkflowSignal } from "@/api/workflows";
import { useCampaignContext } from "@/contexts/CampaignContext";
import { useProductContext } from "@/contexts/ProductContext";
import { cn } from "@/lib/utils";
import type { ExperimentSpec } from "@/types/artifacts";

// ---------------------------------------------------------------------------
// Local types
// ---------------------------------------------------------------------------

type ExperimentVariantEditDraft = {
  id: string;
  name: string;
  description: string;
  channelsText: string;
  guardrailsText: string;
};

type ExperimentSpecEditDraft = {
  id: string;
  name: string;
  hypothesis: string;
  metricIdsText: string;
  sampleSizeEstimateText: string;
  durationDaysText: string;
  budgetEstimateText: string;
  variants: ExperimentVariantEditDraft[];
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function normalizeListText(value: string) {
  const items = value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item)) return false;
    seen.add(item);
    return true;
  });
}

const READABILITY_MAX_WIDTH_CLASS = "w-full max-w-4xl";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CampaignAnglesTab() {
  const navigate = useNavigate();
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { product } = useProductContext();
  const {
    campaignId,
    campaign,
    experimentSpecs,
    experimentsLoading,
    funnels,
    campaignWorkflows,
    latestFunnelWorkflow,
    funnelLogs,
  } = useCampaignContext();

  const updateExperimentSpecs = useUpdateExperimentSpecs(campaignId);

  // ---- Local state --------------------------------------------------------
  const [experimentDrafts, setExperimentDrafts] = useState<ExperimentSpec[]>([]);
  const [selectedExperimentIds, setSelectedExperimentIds] = useState<string[]>([]);
  const [selectedVariantIdsByExperiment, setSelectedVariantIdsByExperiment] = useState<Record<string, string[]>>({});
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingSpec, setEditingSpec] = useState<ExperimentSpec | null>(null);
  const [editingDraft, setEditingDraft] = useState<ExperimentSpecEditDraft | null>(null);
  const [editingError, setEditingError] = useState<string | null>(null);
  const [funnelGenerationPending, setFunnelGenerationPending] = useState(false);
  const [funnelGenerationError, setFunnelGenerationError] = useState<string | null>(null);
  const [funnelCreationRequested, setFunnelCreationRequested] = useState(false);

  // ---- Derived state ------------------------------------------------------
  const planningWorkflow = campaignWorkflows.find((wf) => wf.kind === "campaign_planning" && wf.status === "running");
  const funnelWorkflow = campaignWorkflows.find(
    (wf) => wf.kind === "campaign_funnel_generation" && wf.status === "running",
  );
  const hasRunningFunnelWorkflow = Boolean(funnelWorkflow?.id);
  const planningSignal = useWorkflowSignal(planningWorkflow?.id);
  const canApproveExperiments = Boolean(planningWorkflow?.id);
  const isFunnelGenerationActive = funnelGenerationPending || funnelCreationRequested || hasRunningFunnelWorkflow;

  const latestFunnelFailure = useMemo(() => {
    if (!funnelLogs.length) return null;
    const failures = funnelLogs.filter((log) => log.status === "failed");
    if (!failures.length) return null;
    return [...failures].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )[0];
  }, [funnelLogs]);

  const funnelFailureSummary = useMemo(() => {
    if (!latestFunnelFailure) return null;
    const stepLabel = latestFunnelFailure.step.replace(/_/g, " ");
    const when = formatDate(latestFunnelFailure.created_at);
    const detail = latestFunnelFailure.error || "Unknown error.";
    return `${stepLabel} failed at ${when}. ${detail}`;
  }, [latestFunnelFailure]);

  const experimentNameById = useMemo(() => {
    const map: Record<string, string> = {};
    experimentDrafts.forEach((spec) => {
      if (spec.id) map[spec.id] = spec.name || spec.id;
    });
    return map;
  }, [experimentDrafts]);

  const existingFunnelExperimentIds = useMemo(() => {
    const ids = new Set<string>();
    funnels.forEach((funnel) => {
      if (!funnel.experiment_spec_id) return;
      const normalized = funnel.experiment_spec_id.trim();
      if (normalized) ids.add(normalized);
    });
    return ids;
  }, [funnels]);

  const selectedExperimentsWithFunnels = useMemo(
    () => selectedExperimentIds.filter((id) => existingFunnelExperimentIds.has(id)),
    [selectedExperimentIds, existingFunnelExperimentIds],
  );
  const selectedExperimentsWithFunnelsLabel = useMemo(
    () => selectedExperimentsWithFunnels.map((id) => experimentNameById[id] || id).join(", "),
    [selectedExperimentsWithFunnels, experimentNameById],
  );

  const allVariantIdsByExperiment = useMemo(() => {
    const next: Record<string, string[]> = {};
    experimentDrafts.forEach((spec) => {
      next[spec.id] = (spec.variants || [])
        .map((variant) => variant.id)
        .filter((variantId): variantId is string => Boolean(variantId));
    });
    return next;
  }, [experimentDrafts]);

  // ---- Sync effects -------------------------------------------------------

  useEffect(() => {
    setExperimentDrafts(experimentSpecs);
  }, [experimentSpecs]);

  useEffect(() => {
    setSelectedExperimentIds((prev) => prev.filter((id) => experimentSpecs.some((spec) => spec.id === id)));
  }, [experimentSpecs]);

  useEffect(() => {
    setSelectedVariantIdsByExperiment((prev) => {
      const selectedIds = new Set(selectedExperimentIds);
      const next: Record<string, string[]> = {};
      selectedIds.forEach((experimentId) => {
        const availableVariantIds = allVariantIdsByExperiment[experimentId] || [];
        if (!availableVariantIds.length) {
          next[experimentId] = [];
          return;
        }
        const previousSelection = prev[experimentId] || [];
        const filteredSelection = previousSelection.filter((variantId) => availableVariantIds.includes(variantId));
        next[experimentId] = filteredSelection.length ? filteredSelection : [...availableVariantIds];
      });
      return next;
    });
  }, [allVariantIdsByExperiment, selectedExperimentIds]);

  useEffect(() => {
    if (funnels.length && funnelCreationRequested) {
      setFunnelCreationRequested(false);
    }
  }, [funnels.length, funnelCreationRequested]);

  // ---- Selection helpers --------------------------------------------------
  const allExperimentIds = useMemo(() => experimentDrafts.map((spec) => spec.id).filter(Boolean), [experimentDrafts]);
  const allExperimentsSelected =
    allExperimentIds.length > 0 && allExperimentIds.every((id) => selectedExperimentIds.includes(id));

  const toggleExperimentSelection = (id: string) => {
    setSelectedExperimentIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };
  const toggleAllExperiments = () => {
    setSelectedExperimentIds(allExperimentsSelected ? [] : allExperimentIds);
  };

  const selectedVariantCount = useMemo(() => {
    if (!selectedExperimentIds.length) return 0;
    return selectedExperimentIds.reduce((sum, experimentId) => {
      return sum + (selectedVariantIdsByExperiment[experimentId]?.length || 0);
    }, 0);
  }, [selectedExperimentIds, selectedVariantIdsByExperiment]);

  const toggleVariantSelection = (experimentId: string, variantId: string) => {
    setSelectedVariantIdsByExperiment((prev) => {
      const availableVariantIds = allVariantIdsByExperiment[experimentId] || [];
      if (!availableVariantIds.includes(variantId)) return prev;
      const currentSelection = prev[experimentId] || [];
      const nextSelection = currentSelection.includes(variantId)
        ? currentSelection.filter((id) => id !== variantId)
        : [...currentSelection, variantId];
      const orderedSelection = availableVariantIds.filter((id) => nextSelection.includes(id));
      return { ...prev, [experimentId]: orderedSelection };
    });
  };

  const toggleAllVariantsForExperiment = (experimentId: string) => {
    setSelectedVariantIdsByExperiment((prev) => {
      const availableVariantIds = allVariantIdsByExperiment[experimentId] || [];
      if (!availableVariantIds.length) return prev;
      const currentSelection = prev[experimentId] || [];
      const hasAllSelected =
        availableVariantIds.length > 0 && availableVariantIds.every((variantId) => currentSelection.includes(variantId));
      return {
        ...prev,
        [experimentId]: hasAllSelected ? [] : [...availableVariantIds],
      };
    });
  };

  // ---- Handlers -----------------------------------------------------------

  const getErrorMessage = (err: unknown) => {
    if (typeof err === "string") return err;
    if (err && typeof err === "object" && "message" in err) return (err as ApiError).message || "Request failed";
    return "Request failed";
  };

  const handleApproveExperiments = () => {
    if (!planningWorkflow?.id) return;
    planningSignal.mutate({
      signal: "approve-experiments",
      body: { approved_ids: selectedExperimentIds, rejected_ids: [] },
    });
  };

  const handleCreateFunnels = async () => {
    setFunnelGenerationError(null);
    if (!selectedExperimentIds.length) {
      setFunnelGenerationError("Select at least one angle to create funnels.");
      return;
    }
    if (selectedExperimentsWithFunnels.length) {
      setFunnelGenerationError(
        `Funnels already exist for: ${selectedExperimentsWithFunnelsLabel}. Unselect those angles before creating funnels.`,
      );
      return;
    }
    if (hasRunningFunnelWorkflow) {
      setFunnelGenerationError(
        "A funnel generation workflow is already running for this campaign. Wait for it to finish before creating more.",
      );
      return;
    }
    const missingVariantSelection = selectedExperimentIds.find(
      (experimentId) => (selectedVariantIdsByExperiment[experimentId] || []).length === 0,
    );
    if (missingVariantSelection) {
      setFunnelGenerationError(
        `Select at least one variant for angle ${experimentNameById[missingVariantSelection] || missingVariantSelection}.`,
      );
      return;
    }
    if (!campaign.product_id && !product?.id) {
      setFunnelGenerationError("Campaign is missing a product. Attach a product to start funnel generation.");
      return;
    }
    if (!campaign.channels?.length) {
      setFunnelGenerationError("Campaign is missing channels. Add channels before creating funnels.");
      return;
    }
    if (!campaign.asset_brief_types?.length) {
      setFunnelGenerationError("Campaign is missing creative brief types. Add them before creating funnels.");
      return;
    }

    setFunnelGenerationPending(true);
    setFunnelCreationRequested(true);
    try {
      const variantIdsByExperiment = selectedExperimentIds.reduce<Record<string, string[]>>((acc, experimentId) => {
        const selectedVariantIds = selectedVariantIdsByExperiment[experimentId] || [];
        acc[experimentId] = selectedVariantIds;
        return acc;
      }, {});
      const response = await post<{ workflow_run_id: string }>(
        `/campaigns/${campaign.id}/funnels/generate`,
        {
          experimentIds: selectedExperimentIds,
          variantIdsByExperiment,
          generateTestimonials: true,
        },
      );
      if (!response?.workflow_run_id) {
        setFunnelGenerationError("Funnel generation started but no workflow id was returned.");
        setFunnelCreationRequested(false);
        return;
      }
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      queryClient.invalidateQueries({ queryKey: ["funnels"] });
    } catch (err) {
      setFunnelGenerationError(`Failed to start funnel generation: ${getErrorMessage(err)}`);
      setFunnelCreationRequested(false);
    } finally {
      setFunnelGenerationPending(false);
    }
  };

  // ---- Edit spec handlers -------------------------------------------------

  const openEditSpec = (spec: ExperimentSpec) => {
    setEditingSpec(spec);
    setEditingDraft({
      id: spec.id,
      name: spec.name || "",
      hypothesis: spec.hypothesis || "",
      metricIdsText: (spec.metricIds || []).join("\n"),
      sampleSizeEstimateText: spec.sampleSizeEstimate ? String(spec.sampleSizeEstimate) : "",
      durationDaysText: spec.durationDays ? String(spec.durationDays) : "",
      budgetEstimateText: spec.budgetEstimate ? String(spec.budgetEstimate) : "",
      variants: (spec.variants || []).map((variant) => ({
        id: variant.id,
        name: variant.name || "",
        description: variant.description || "",
        channelsText: (variant.channels || []).join("\n"),
        guardrailsText: (variant.guardrails || []).join("\n"),
      })),
    });
    setEditingError(null);
    setEditDialogOpen(true);
  };

  const handleSaveSpec = () => {
    if (!editingSpec || !editingDraft) {
      setEditingError("Angle spec is required to save edits.");
      return;
    }

    const parseOptionalPositiveInt = (raw: string, label: string) => {
      const trimmed = raw.trim();
      if (!trimmed) return { value: undefined as number | undefined };
      const num = Number(trimmed);
      if (!Number.isFinite(num) || !Number.isInteger(num)) {
        return { error: `${label} must be a whole number.` };
      }
      if (num <= 0) {
        return { error: `${label} must be greater than 0.` };
      }
      return { value: num };
    };

    if (!editingDraft.id || editingDraft.id !== editingSpec.id) {
      setEditingError("Angle spec id cannot be changed.");
      return;
    }

    const name = editingDraft.name.trim();
    if (!name) {
      setEditingError("Angle name is required.");
      return;
    }

    const metricIds = normalizeListText(editingDraft.metricIdsText);
    if (!metricIds.length) {
      setEditingError("Angle must include at least one metric id.");
      return;
    }

    if (!editingDraft.variants.length) {
      setEditingError("Angle must include at least one variant.");
      return;
    }

    const nextVariants = editingDraft.variants.map((variant) => {
      const variantName = variant.name.trim();
      const description = variant.description.trim();
      const channels = normalizeListText(variant.channelsText);
      const guardrails = normalizeListText(variant.guardrailsText);
      return {
        id: variant.id,
        name: variantName,
        ...(description ? { description } : {}),
        ...(channels.length ? { channels } : {}),
        ...(guardrails.length ? { guardrails } : {}),
      };
    });

    const invalidVariant = nextVariants.find((variant) => !variant.id || !variant.name);
    if (invalidVariant) {
      setEditingError("Each variant must include an id and a name.");
      return;
    }

    const sampleSizeResult = parseOptionalPositiveInt(editingDraft.sampleSizeEstimateText, "Sample size");
    if (sampleSizeResult.error) {
      setEditingError(sampleSizeResult.error);
      return;
    }
    const durationResult = parseOptionalPositiveInt(editingDraft.durationDaysText, "Duration (days)");
    if (durationResult.error) {
      setEditingError(durationResult.error);
      return;
    }
    const budgetResult = parseOptionalPositiveInt(editingDraft.budgetEstimateText, "Budget");
    if (budgetResult.error) {
      setEditingError(budgetResult.error);
      return;
    }

    const parsed: ExperimentSpec = {
      ...editingSpec,
      id: editingSpec.id,
      name,
      hypothesis: editingDraft.hypothesis.trim() || undefined,
      metricIds,
      variants: nextVariants,
      sampleSizeEstimate: sampleSizeResult.value,
      durationDays: durationResult.value,
      budgetEstimate: budgetResult.value,
    };

    const nextSpecs = experimentDrafts.map((spec) => (spec.id === parsed.id ? parsed : spec));
    setExperimentDrafts(nextSpecs);
    updateExperimentSpecs.mutate(
      { experimentSpecs: nextSpecs },
      {
        onSuccess: () => {
          setEditDialogOpen(false);
          setEditingSpec(null);
          setEditingDraft(null);
        },
      },
    );
  };

  // ---- Render -------------------------------------------------------------

  return (
    <div className={READABILITY_MAX_WIDTH_CLASS}>
      {experimentsLoading ? (
        <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
          Loading angles…
        </div>
      ) : experimentDrafts.length ? (
        <div className="rounded-xl border border-border bg-transparent">
          <div className="border-b border-border px-4 py-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-base font-semibold text-content">Angle specs</div>
                <div className="text-sm text-content-muted">Generated from canon and metric schema.</div>
              </div>
              <div className="flex items-center gap-2">
                {canApproveExperiments ? (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleApproveExperiments}
                    disabled={planningSignal.isPending || selectedExperimentIds.length === 0}
                  >
                    {planningSignal.isPending ? "Sending…" : "Approve experiments"}
                  </Button>
                ) : null}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCreateFunnels}
                  disabled={
                    funnelGenerationPending ||
                    isFunnelGenerationActive ||
                    selectedExperimentIds.length === 0 ||
                    selectedExperimentsWithFunnels.length > 0
                  }
                >
                  {funnelGenerationPending || isFunnelGenerationActive ? "Creating…" : "Create funnels"}
                </Button>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-content-muted">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  className={cn(
                    "h-4 w-4 rounded border border-border bg-surface text-accent",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30",
                  )}
                  checked={allExperimentsSelected}
                  onChange={toggleAllExperiments}
                />
                <span>Select all</span>
              </label>
              <span>
                {selectedExperimentIds.length} angles selected · {selectedVariantCount} variants included
              </span>
              {updateExperimentSpecs.isPending ? <span>Saving edits…</span> : null}
            </div>
            <div className="mt-2 space-y-2 text-sm text-content-muted">
              <div>Select angles to approve or create funnels. Uncheck variants for lighter tests.</div>
              {selectedExperimentsWithFunnels.length ? (
                <div className="text-danger">
                  Funnels already exist for: {selectedExperimentsWithFunnelsLabel}. Unselect these angles to
                  avoid duplicate workflows.
                </div>
              ) : null}
              {hasRunningFunnelWorkflow ? (
                <div className="text-danger">
                  A funnel generation workflow is already running for this campaign. Wait for completion before
                  creating more funnels.
                </div>
              ) : null}
              {funnelGenerationError ? <div className="text-danger">{funnelGenerationError}</div> : null}
              {funnelFailureSummary ? (
                <div className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                  <div className="font-semibold">Funnel generation failed</div>
                  <div>{funnelFailureSummary}</div>
                  {latestFunnelWorkflow?.id ? (
                    <Button
                      variant="secondary"
                      size="xs"
                      className="mt-2"
                      onClick={() => navigate(`/strategy/${latestFunnelWorkflow.id}`)}
                    >
                      Open workflow
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>
            {isFunnelGenerationActive ? (
              <div className="mt-2 text-sm text-content-muted">
                Creating funnels… They will appear in the Funnels tab once ready.
              </div>
            ) : null}
          </div>
          <div className="space-y-4 p-4">
            {experimentDrafts.map((exp) => {
              const isSelected = selectedExperimentIds.includes(exp.id);
              const availableVariantIds = (exp.variants || [])
                .map((variant) => variant.id)
                .filter((variantId): variantId is string => Boolean(variantId));
              const selectedVariantIds = selectedVariantIdsByExperiment[exp.id] || [];
              const selectedVariantSet = new Set(selectedVariantIds);
              const allVariantsSelectedForExperiment =
                availableVariantIds.length > 0 &&
                availableVariantIds.every((variantId) => selectedVariantSet.has(variantId));
              return (
                <div
                  key={exp.id}
                  className={cn(
                    "rounded-xl border border-border bg-surface p-4 shadow-sm",
                    isSelected && "border-accent/30 ring-2 ring-accent/10",
                  )}
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="flex min-w-0 items-start gap-3">
                      <input
                        type="checkbox"
                        className={cn(
                          "mt-1 h-4 w-4 rounded border border-border bg-surface text-accent",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30",
                        )}
                        checked={isSelected}
                        onChange={() => toggleExperimentSelection(exp.id)}
                      />
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-base font-semibold text-content">{exp.name || exp.id}</div>
                          {isSelected ? <Badge tone="accent">Selected</Badge> : null}
                          {existingFunnelExperimentIds.has(exp.id) ? <Badge tone="neutral">Funnels created</Badge> : null}
                          <Badge tone="neutral">{(exp.variants || []).length} variants</Badge>
                        </div>
                        <div className="mt-0.5 text-xs font-mono text-content-muted">{exp.id}</div>
                        {exp.hypothesis ? (
                          <div className="mt-2 text-sm text-content-muted">{exp.hypothesis}</div>
                        ) : null}
                        <div className="mt-3 flex flex-wrap gap-2 text-xs text-content-muted">
                          <span className="rounded-full bg-muted px-2.5 py-1">
                            Metrics: {(exp.metricIds || []).join(", ") || "—"}
                          </span>
                          <span className="rounded-full bg-muted px-2.5 py-1">
                            Sample size: {exp.sampleSizeEstimate ?? "—"}
                          </span>
                          <span className="rounded-full bg-muted px-2.5 py-1">
                            Duration: {exp.durationDays ?? "—"} days
                          </span>
                          <span className="rounded-full bg-muted px-2.5 py-1">
                            Budget: {exp.budgetEstimate ?? "—"}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        variant="secondary"
                        size="xs"
                        onClick={() => openEditSpec(exp)}
                        disabled={updateExperimentSpecs.isPending}
                      >
                        Edit angle
                      </Button>
                    </div>
                  </div>

                  {exp.variants?.length ? (
                    <div className="mt-4 rounded-lg bg-muted p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                          Variants
                        </div>
                        <div className="flex items-center gap-3 text-xs text-content-muted">
                          <span>
                            {selectedVariantIds.length}/{availableVariantIds.length} selected
                          </span>
                          <label className="flex items-center gap-1.5">
                            <input
                              type="checkbox"
                              className={cn(
                                "h-3.5 w-3.5 rounded border border-border bg-surface text-accent",
                                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30",
                              )}
                              checked={allVariantsSelectedForExperiment}
                              onChange={() => toggleAllVariantsForExperiment(exp.id)}
                              disabled={!isSelected}
                            />
                            <span>Select all variants</span>
                          </label>
                        </div>
                      </div>
                      <div className="mt-2 space-y-2">
                        {exp.variants.map((variant) => (
                          <div key={variant.id} className="rounded-md bg-surface px-3 py-2">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div className="flex min-w-0 flex-1 items-start gap-2">
                                <input
                                  type="checkbox"
                                  className={cn(
                                    "mt-1 h-4 w-4 rounded border border-border bg-surface text-accent",
                                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30",
                                  )}
                                  checked={selectedVariantSet.has(variant.id)}
                                  onChange={() => toggleVariantSelection(exp.id, variant.id)}
                                  disabled={!isSelected}
                                />
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-content">
                                    {variant.name || variant.id}
                                    {selectedVariantSet.has(variant.id) ? (
                                      <Badge tone="accent" className="ml-2">
                                        Included
                                      </Badge>
                                    ) : (
                                      <Badge tone="neutral" className="ml-2">
                                        Excluded
                                      </Badge>
                                    )}
                                  </div>
                                  {variant.description ? (
                                    <div className="mt-1 text-sm text-content-muted">{variant.description}</div>
                                  ) : null}
                                </div>
                              </div>
                              <div className="shrink-0 font-mono text-xs text-content-muted">{variant.id}</div>
                            </div>
                            <div className="mt-2 text-xs text-content-muted">
                              Channels: {(variant.channels || []).join(", ") || "—"}
                            </div>
                            {variant.guardrails?.length ? (
                              <div className="mt-1 text-xs text-content-muted">
                                Guardrails: {variant.guardrails.join("; ")}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="mt-4 text-sm text-content-muted">No variants.</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="border border-border bg-transparent px-4 py-3 text-base">
          No angle specs generated yet. Start campaign planning to generate angles.
        </div>
      )}

      {/* Edit angle dialog */}
      <DialogRoot
        open={editDialogOpen}
        onOpenChange={(open) => {
          setEditDialogOpen(open);
          if (!open) {
            setEditingSpec(null);
            setEditingDraft(null);
            setEditingError(null);
          }
        }}
      >
        <DialogContent className="max-w-4xl">
          <div className="space-y-2">
            <DialogTitle>Edit angle</DialogTitle>
            <DialogDescription>
              Update angle and variant details. IDs are locked so downstream assets can link correctly.
            </DialogDescription>
            {editingSpec ? (
              <div className="text-sm text-content-muted">
                Angle ID: <span className="font-mono">{editingSpec.id}</span>
              </div>
            ) : null}
          </div>

          {editingError ? (
            <div className="mt-4 rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
              {editingError}
            </div>
          ) : null}

          {editingDraft ? (
            <div className="mt-4 max-h-[70vh] space-y-6 overflow-y-auto pr-1">
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Angle name</label>
                    <Input
                      value={editingDraft.name}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, name: value } : prev));
                        setEditingError(null);
                      }}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Metrics (one per line)</label>
                    <Textarea
                      rows={4}
                      value={editingDraft.metricIdsText}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, metricIdsText: value } : prev));
                        setEditingError(null);
                      }}
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-semibold text-content">Hypothesis</label>
                  <Textarea
                    rows={3}
                    value={editingDraft.hypothesis}
                    onChange={(e) => {
                      const value = e.target.value;
                      setEditingDraft((prev) => (prev ? { ...prev, hypothesis: value } : prev));
                      setEditingError(null);
                    }}
                  />
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Sample size</label>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      value={editingDraft.sampleSizeEstimateText}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, sampleSizeEstimateText: value } : prev));
                        setEditingError(null);
                      }}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Duration (days)</label>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      value={editingDraft.durationDaysText}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, durationDaysText: value } : prev));
                        setEditingError(null);
                      }}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Budget</label>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      value={editingDraft.budgetEstimateText}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, budgetEstimateText: value } : prev));
                        setEditingError(null);
                      }}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="text-sm font-semibold text-content">Variants</div>
                  <div className="text-xs text-content-muted">Variant IDs are locked.</div>
                </div>
                <div className="space-y-3">
                  {editingDraft.variants.map((variant) => (
                    <div key={variant.id} className="rounded-xl bg-muted p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="text-sm font-semibold text-content">
                          Variant: {variant.name || variant.id}
                        </div>
                        <div className="text-xs font-mono text-content-muted">{variant.id}</div>
                      </div>

                      <div className="mt-3 grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <label className="text-sm font-semibold text-content">Name</label>
                          <Input
                            value={variant.name}
                            onChange={(e) => {
                              const value = e.target.value;
                              setEditingDraft((prev) => {
                                if (!prev) return prev;
                                return {
                                  ...prev,
                                  variants: prev.variants.map((item) =>
                                    item.id === variant.id ? { ...item, name: value } : item,
                                  ),
                                };
                              });
                              setEditingError(null);
                            }}
                            required
                          />
                        </div>
                        <div className="space-y-2">
                          <label className="text-sm font-semibold text-content">Channels (one per line)</label>
                          <Textarea
                            rows={3}
                            value={variant.channelsText}
                            onChange={(e) => {
                              const value = e.target.value;
                              setEditingDraft((prev) => {
                                if (!prev) return prev;
                                return {
                                  ...prev,
                                  variants: prev.variants.map((item) =>
                                    item.id === variant.id ? { ...item, channelsText: value } : item,
                                  ),
                                };
                              });
                              setEditingError(null);
                            }}
                          />
                        </div>
                      </div>

                      <div className="mt-3 space-y-2">
                        <label className="text-sm font-semibold text-content">Description</label>
                        <Textarea
                          rows={3}
                          value={variant.description}
                          onChange={(e) => {
                            const value = e.target.value;
                            setEditingDraft((prev) => {
                              if (!prev) return prev;
                              return {
                                ...prev,
                                variants: prev.variants.map((item) =>
                                  item.id === variant.id ? { ...item, description: value } : item,
                                ),
                              };
                            });
                            setEditingError(null);
                          }}
                        />
                      </div>

                      <div className="mt-3 space-y-2">
                        <label className="text-sm font-semibold text-content">Guardrails (one per line)</label>
                        <Textarea
                          rows={3}
                          value={variant.guardrailsText}
                          onChange={(e) => {
                            const value = e.target.value;
                            setEditingDraft((prev) => {
                              if (!prev) return prev;
                              return {
                                ...prev,
                                variants: prev.variants.map((item) =>
                                  item.id === variant.id ? { ...item, guardrailsText: value } : item,
                                ),
                              };
                            });
                            setEditingError(null);
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-4 rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
              No angle loaded for editing.
            </div>
          )}

          <div className="mt-4 flex items-center justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSaveSpec} disabled={updateExperimentSpecs.isPending || !editingDraft}>
              {updateExperimentSpecs.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
