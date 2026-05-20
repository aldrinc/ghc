import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Edit, Loader2, Plus, Trash2, Funnel, Save, X } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useSite } from "@/api/sites";
import {
  useSiteFunnel,
  useUpdateSiteFunnel,
  useCreateSiteFunnelStep,
  useDeleteSiteFunnelStep,
  useCreateSiteFunnelStepOption,
  useDeleteSiteFunnelStepOption,
  useCreateSiteFunnelPath,
  useDeleteSiteFunnelPath,
} from "@/api/siteFunnels";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

function formatFunnelStatus(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "active") return "success";
  if (status === "draft") return "warning";
  if (status === "archived") return "danger";
  return "neutral";
}

export function SiteFunnelDetailPage() {
  const { siteId, funnelId } = useParams<{ siteId: string; funnelId: string }>();
  const { workspace } = useWorkspace();
  const navigate = useNavigate();
  
  const { data: site, isLoading: siteLoading } = useSite(siteId || null);
  const { data: funnel, isLoading: funnelLoading } = useSiteFunnel(siteId || null, funnelId || null);
  const updateFunnel = useUpdateSiteFunnel(siteId || null, funnelId || null);
  const createStep = useCreateSiteFunnelStep(siteId || null, funnelId || null);
  const deleteStep = useDeleteSiteFunnelStep(siteId || null, funnelId || null);
  const createStepOption = useCreateSiteFunnelStepOption(siteId || null, funnelId || null);
  const deleteStepOption = useDeleteSiteFunnelStepOption(siteId || null, funnelId || null);
  const createPath = useCreateSiteFunnelPath(siteId || null, funnelId || null);
  const deletePath = useDeleteSiteFunnelPath(siteId || null, funnelId || null);

  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editStatus, setEditStatus] = useState<string>("");
  const [showAddStepForm, setShowAddStepForm] = useState(false);
  const [selectedPageId, setSelectedPageId] = useState("");
  const [stepRole, setStepRole] = useState("");
  const [deletingStepId, setDeletingStepId] = useState<string | null>(null);
  const [activeOptionStepId, setActiveOptionStepId] = useState<string | null>(null);
  const [selectedOptionPageId, setSelectedOptionPageId] = useState("");
  const [optionKey, setOptionKey] = useState("");
  const [optionLabel, setOptionLabel] = useState("");
  const [deletingOptionId, setDeletingOptionId] = useState<string | null>(null);
  const [showCreatePathForm, setShowCreatePathForm] = useState(false);
  const [pathName, setPathName] = useState("");
  const [pathSlug, setPathSlug] = useState("");
  const [pathSelectionsByStepId, setPathSelectionsByStepId] = useState<Record<string, string>>({});
  const [deletingPathId, setDeletingPathId] = useState<string | null>(null);

  const isLoading = siteLoading || funnelLoading;

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site Funnel" description="View funnel details." />
        <EmptyState
          title="No workspace selected"
          description="Select a workspace to view funnel details."
        />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site Funnel" description="View funnel details.">
          <div className="flex items-center gap-2 text-sm text-content-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading...
          </div>
        </PageHeader>
      </div>
    );
  }

  if (!site || !funnel) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site Funnel" description="View funnel details." />
        <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          Failed to load funnel details.
        </div>
        <Button variant="outline" onClick={() => navigate(`/workspaces/sites/${siteId}`)}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Site
        </Button>
      </div>
    );
  }

  const handleStartEdit = () => {
    setEditName(funnel.name);
    setEditDescription(funnel.description || "");
    setEditStatus(funnel.status);
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    try {
      await updateFunnel.mutateAsync({
        name: editName,
        description: editDescription || null,
        status: editStatus as "draft" | "active" | "paused" | "archived",
      });
      setIsEditing(false);
    } catch (error) {
      console.error("Failed to update funnel:", error);
    }
  };

  const handleAddStep = async () => {
    if (!selectedPageId) return;
    try {
      await createStep.mutateAsync({
        sitePageId: selectedPageId,
        stepRole: stepRole || undefined,
      });
      setShowAddStepForm(false);
      setSelectedPageId("");
      setStepRole("");
    } catch (error) {
      console.error("Failed to add step:", error);
    }
  };

  const handleDeleteStep = async (stepId: string) => {
    setDeletingStepId(stepId);
    try {
      await deleteStep.mutateAsync(stepId);
    } finally {
      setDeletingStepId(null);
    }
  };

  const handleAddStepOption = async () => {
    if (!activeOptionStepId || !selectedOptionPageId || !optionKey.trim() || !optionLabel.trim()) return;
    try {
      await createStepOption.mutateAsync({
        stepId: activeOptionStepId,
        request: {
          sitePageId: selectedOptionPageId,
          optionKey: optionKey.trim(),
          label: optionLabel.trim(),
          status: "draft",
        },
      });
      setActiveOptionStepId(null);
      setSelectedOptionPageId("");
      setOptionKey("");
      setOptionLabel("");
    } catch (error) {
      console.error("Failed to add step option:", error);
    }
  };

  const handleDeleteStepOption = async (stepId: string, optionId: string) => {
    setDeletingOptionId(optionId);
    try {
      await deleteStepOption.mutateAsync({ stepId, optionId });
    } finally {
      setDeletingOptionId(null);
    }
  };

  const sortedSteps = [...(funnel?.steps ?? [])].sort((a, b) => a.ordering - b.ordering);
  const canCreatePath =
    pathName.trim().length > 0 &&
    pathSlug.trim().length > 0 &&
    sortedSteps.length > 0 &&
    sortedSteps.every((step) => Boolean(pathSelectionsByStepId[step.id]));

  const handleCreatePath = async () => {
    if (!canCreatePath) return;
    try {
      await createPath.mutateAsync({
        name: pathName.trim(),
        slug: pathSlug.trim(),
        status: "draft",
        steps: sortedSteps.map((step) => ({
          siteFunnelStepId: step.id,
          sitePageId: pathSelectionsByStepId[step.id],
        })),
      });
      setShowCreatePathForm(false);
      setPathName("");
      setPathSlug("");
      setPathSelectionsByStepId({});
    } catch (error) {
      console.error("Failed to create funnel path:", error);
    }
  };

  const handleDeletePath = async (pathId: string) => {
    setDeletingPathId(pathId);
    try {
      await deletePath.mutateAsync(pathId);
    } finally {
      setDeletingPathId(null);
    }
  };

  const pageOptions = site.pages.map((page) => ({
    label: `${page.name} (/${page.slug})`,
    value: page.id,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title={isEditing ? "Edit Funnel" : funnel.name}
        description={isEditing ? "Update funnel details" : (funnel.description || `${site.name} funnel`)}
      >
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-content-muted">
          <Badge tone="neutral">Site: {site.name}</Badge>
          <Badge tone={formatFunnelStatus(funnel.status)}>{funnel.status}</Badge>
        </div>
      </PageHeader>

      {/* Edit Form */}
      {isEditing ? (
        <div className="rounded-2xl border border-border bg-surface px-4 py-4 space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Funnel Name</label>
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder="Funnel name"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Description</label>
            <Input
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              placeholder="Funnel description"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Status</label>
            <select
              className="w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content"
              value={editStatus}
              onChange={(e) => setEditStatus(e.target.value)}
            >
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="archived">Archived</option>
            </select>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSaveEdit} disabled={updateFunnel.isPending}>
              {updateFunnel.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              Save Changes
            </Button>
            <Button variant="outline" onClick={() => setIsEditing(false)}>
              <X className="mr-2 h-4 w-4" />
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <>
          {/* Funnel Info */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Funnel Information</div>
                <div className="text-xs text-content-muted">
                  Details and configuration for this funnel.
                </div>
              </div>
              <Button size="sm" variant="outline" onClick={handleStartEdit}>
                <Edit className="mr-1 h-4 w-4" />
                Edit
              </Button>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Status
                </div>
                <div className="mt-1">
                  <Badge tone={formatFunnelStatus(funnel.status)}>{funnel.status}</Badge>
                </div>
              </div>

              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Entry Page
                </div>
                <div className="mt-1 text-sm font-semibold text-content">
                  {funnel.entryPageId ? (
                    site.pages.find((p) => p.id === funnel.entryPageId)?.name || "Unknown page"
                  ) : (
                    <span className="text-content-muted">Not set</span>
                  )}
                </div>
              </div>

              {funnel.productId && (
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Product
                  </div>
                  <div className="mt-1 text-sm font-semibold text-content">
                    {funnel.productId.slice(0, 8)}...
                  </div>
                </div>
              )}

              {funnel.selectedOfferId && (
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Selected Offer
                  </div>
                  <div className="mt-1 text-sm font-semibold text-content">
                    {funnel.selectedOfferId.slice(0, 8)}...
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Funnel Steps */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Funnel Steps</div>
                <div className="text-xs text-content-muted">
                  Ordered pages in this funnel's conversion path.
                </div>
              </div>
              <Button size="sm" onClick={() => setShowAddStepForm(true)}>
                <Plus className="mr-1 h-4 w-4" />
                Add Step
              </Button>
            </div>

            {funnel.steps.length === 0 ? (
              <div className="py-6 text-sm text-content-muted">
                No steps yet. Add pages to define the funnel path.
              </div>
            ) : (
              <div className="mt-4 space-y-2">
                {sortedSteps.map((step, index) => (
                    <div
                      key={step.id}
                      className={cn(
                        "rounded-xl border px-4 py-3 transition-colors",
                        "border-border bg-surface-2 hover:border-accent/40"
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/10 text-accent font-semibold text-sm">
                            {index + 1}
                          </div>
                          <div>
                            <div className="text-sm font-semibold text-content">
                              {step.page.name}
                            </div>
                            <div className="text-xs text-content-muted">
                              /{step.page.slug}
                              {step.stepRole && ` • ${step.stepRole}`}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              navigate(`/workspaces/sites/${site.id}/pages/${step.sitePageId}`)
                            }
                          >
                            <Edit className="mr-1 h-3 w-3" />
                            Edit Page
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setActiveOptionStepId(step.id);
                              setSelectedOptionPageId("");
                              setOptionKey("");
                              setOptionLabel("");
                            }}
                          >
                            <Plus className="mr-1 h-3 w-3" />
                            Option
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => handleDeleteStep(step.id)}
                            disabled={deletingStepId === step.id}
                          >
                            {deletingStepId === step.id ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Trash2 className="h-3 w-3" />
                            )}
                          </Button>
                        </div>
                      </div>
                      <div className="mt-3 border-t border-border pt-3">
                        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-muted">
                          Page options
                        </div>
                        {step.options?.length ? (
                          <div className="flex flex-wrap gap-2">
                            {step.options.map((option) => (
                              <div
                                key={option.id}
                                className="flex items-center gap-2 rounded-md border border-border bg-surface px-2 py-1 text-xs"
                              >
                                <span className="font-medium text-content">{option.label}</span>
                                <span className="text-content-muted">/{option.page?.slug || option.sitePageId}</span>
                                {option.isControl ? <Badge tone="neutral">control</Badge> : null}
                                <Badge tone={formatFunnelStatus(option.status)}>{option.status}</Badge>
                                {!option.isControl ? (
                                  <button
                                    type="button"
                                    className="text-content-muted hover:text-danger"
                                    onClick={() => void handleDeleteStepOption(step.id, option.id)}
                                    disabled={deletingOptionId === option.id}
                                    aria-label={`Remove option ${option.label}`}
                                  >
                                    {deletingOptionId === option.id ? (
                                      <Loader2 className="h-3 w-3 animate-spin" />
                                    ) : (
                                      <Trash2 className="h-3 w-3" />
                                    )}
                                  </button>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-xs text-content-muted">No page options configured.</div>
                        )}
                        {activeOptionStepId === step.id ? (
                          <div className="mt-3 grid gap-3 md:grid-cols-[1fr_160px_1fr_auto]">
                            <Select
                              options={pageOptions}
                              value={selectedOptionPageId}
                              onValueChange={setSelectedOptionPageId}
                              placeholder="Select page"
                            />
                            <Input
                              value={optionKey}
                              onChange={(e) => setOptionKey(e.target.value)}
                              placeholder="option-key"
                            />
                            <Input
                              value={optionLabel}
                              onChange={(e) => setOptionLabel(e.target.value)}
                              placeholder="Option label"
                            />
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                onClick={() => void handleAddStepOption()}
                                disabled={
                                  !selectedOptionPageId ||
                                  !optionKey.trim() ||
                                  !optionLabel.trim() ||
                                  createStepOption.isPending
                                }
                              >
                                {createStepOption.isPending ? (
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                ) : (
                                  <Plus className="h-3 w-3" />
                                )}
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setActiveOptionStepId(null)}
                              >
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>

          {/* Add Step Form */}
          {showAddStepForm && (
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="text-sm font-semibold text-content mb-4">Add Step</div>
              <div className="space-y-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Page</label>
                  <Select
                    options={pageOptions}
                    value={selectedPageId}
                    onValueChange={setSelectedPageId}
                    placeholder="Select a page"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Step Role (optional)</label>
                  <Input
                    value={stepRole}
                    onChange={(e) => setStepRole(e.target.value)}
                    placeholder="e.g., landing, checkout, thank-you"
                  />
                </div>
                <div className="flex gap-2">
                  <Button onClick={handleAddStep} disabled={!selectedPageId || createStep.isPending}>
                    {createStep.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Plus className="mr-2 h-4 w-4" />
                    )}
                    Add Step
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowAddStepForm(false);
                      setSelectedPageId("");
                      setStepRole("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Funnel Paths */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Internal Paths</div>
                <div className="text-xs text-content-muted">Funnel page combinations</div>
              </div>
              <Button size="sm" onClick={() => setShowCreatePathForm(true)} disabled={!sortedSteps.length}>
                <Plus className="mr-1 h-4 w-4" />
                Add Path
              </Button>
            </div>

            {funnel.paths?.length ? (
              <div className="mt-4 space-y-2">
                {funnel.paths.map((path) => (
                  <div key={path.id} className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-content">{path.name}</span>
                          <Badge tone={formatFunnelStatus(path.status)}>{path.status}</Badge>
                          {path.isControl ? <Badge tone="neutral">control</Badge> : null}
                        </div>
                        <div className="mt-1 text-xs text-content-muted">/{path.slug}</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {path.steps.map((step) => (
                            <span
                              key={step.id}
                              className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-content-muted"
                            >
                              {step.stepRole || `Step ${step.ordering + 1}`}: /{step.page?.slug || step.sitePageId}
                            </span>
                          ))}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => void handleDeletePath(path.id)}
                        disabled={deletingPathId === path.id}
                      >
                        {deletingPathId === path.id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Trash2 className="h-3 w-3" />
                        )}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-6 text-sm text-content-muted">No internal paths yet.</div>
            )}

            {showCreatePathForm ? (
              <div className="mt-4 space-y-4 border-t border-border pt-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Path name</label>
                    <Input
                      value={pathName}
                      onChange={(e) => setPathName(e.target.value)}
                      placeholder="Presell A to Sales Control"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Path slug</label>
                    <Input
                      value={pathSlug}
                      onChange={(e) => setPathSlug(e.target.value)}
                      placeholder="presell-a-sales-control"
                    />
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {sortedSteps.map((step) => (
                    <div key={step.id} className="space-y-1">
                      <label className="text-xs font-semibold text-content">
                        {step.stepRole || `Step ${step.ordering + 1}`}
                      </label>
                      <Select
                        options={[
                          { label: "Select page option", value: "" },
                          ...(step.options || []).map((option) => ({
                            label: `${option.label} (/${option.page?.slug || option.sitePageId})`,
                            value: option.sitePageId,
                          })),
                        ]}
                        value={pathSelectionsByStepId[step.id] || ""}
                        onValueChange={(value) =>
                          setPathSelectionsByStepId((current) => ({ ...current, [step.id]: value }))
                        }
                        placeholder="Select page option"
                      />
                    </div>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button onClick={() => void handleCreatePath()} disabled={!canCreatePath || createPath.isPending}>
                    {createPath.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Plus className="mr-2 h-4 w-4" />
                    )}
                    Create Path
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowCreatePathForm(false);
                      setPathName("");
                      setPathSlug("");
                      setPathSelectionsByStepId({});
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : null}
          </div>

          {/* Quick Actions */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="text-sm font-semibold text-content">Quick Actions</div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => navigate(`/workspaces/sites/${site.id}`)}
              >
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Site
              </Button>
              {funnel.entryPageId && (
                <Button
                  onClick={() =>
                    navigate(`/workspaces/sites/${site.id}/pages/${funnel.entryPageId}`)
                  }
                >
                  <Edit className="mr-2 h-4 w-4" />
                  Edit Entry Page
                </Button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
