import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Edit, Loader2, Plus, Trash2, Funnel, Save, X } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useSite, usePublishSite } from "@/api/sites";
import {
  useSiteFunnel,
  useUpdateSiteFunnel,
  useCreateSiteFunnelStep,
  useDeleteSiteFunnelStep,
  usePrepareSiteFunnel,
} from "@/api/siteFunnels";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

function formatFunnelStatus(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "active") return "success";
  if (status === "draft") return "warning";
  if (status === "archived") return "danger";
  return "neutral";
}

function formatPageIntent(intent: string | null | undefined): string {
  if (intent === "sales") return "Sales";
  if (intent === "pre_sales") return "Pre-sales";
  return "Not set";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function getReadinessFlag(readiness: Record<string, unknown>, key: string): boolean | null {
  const candidate = readiness[key];
  if (!isRecord(candidate)) return null;
  const ready = candidate.ready;
  return typeof ready === "boolean" ? ready : null;
}

function getReadinessRequirement(
  readiness: Record<string, unknown>,
  key: string,
): { required: boolean; ready: boolean | null; detail: Record<string, unknown> | null } {
  const candidate = readiness[key];
  if (!isRecord(candidate)) return { required: false, ready: null, detail: null };
  const required = typeof candidate.required === "boolean" ? candidate.required : false;
  const ready = typeof candidate.ready === "boolean" ? candidate.ready : null;
  return { required, ready, detail: candidate };
}

export function SiteFunnelDetailPage() {
  const { siteId, funnelId } = useParams<{ siteId: string; funnelId: string }>();
  const { workspace } = useWorkspace();
  const navigate = useNavigate();
  
  const { data: site, isLoading: siteLoading } = useSite(siteId || null);
  const publishSite = usePublishSite(siteId || null);
  const { data: funnel, isLoading: funnelLoading } = useSiteFunnel(siteId || null, funnelId || null);
  const updateFunnel = useUpdateSiteFunnel(siteId || null, funnelId || null);
  const createStep = useCreateSiteFunnelStep(siteId || null, funnelId || null);
  const deleteStep = useDeleteSiteFunnelStep(siteId || null, funnelId || null);
  const prepareFunnel = usePrepareSiteFunnel(siteId || null, funnelId || null);

  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editStatus, setEditStatus] = useState<string>("");
  const [showAddStepForm, setShowAddStepForm] = useState(false);
  const [selectedPageId, setSelectedPageId] = useState("");
  const [stepRole, setStepRole] = useState("");
  const [deletingStepId, setDeletingStepId] = useState<string | null>(null);

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

  const pageOptions = site.pages.map((page) => ({
    label: `${page.name} (/${page.slug})`,
    value: page.id,
  }));
  const readiness = isRecord(funnel.preparationReadiness) ? funnel.preparationReadiness : {};
  const navigationReadiness = getReadinessRequirement(readiness, "navigation");
  const checkoutReadiness = getReadinessRequirement(readiness, "checkout");
  const trackingReadiness = getReadinessRequirement(readiness, "tracking");
  const copyReadiness = getReadinessRequirement(readiness, "copy");
  const navigationReady = navigationReadiness.ready;
  const checkoutReady = checkoutReadiness.ready;
  const trackingReady = trackingReadiness.ready;
  const copyReady = copyReadiness.ready;
  const selectedAngleName =
    typeof readiness.selectedAngleName === "string" && readiness.selectedAngleName.trim()
      ? readiness.selectedAngleName.trim()
      : null;
  const copySource =
    copyReadiness.detail && typeof copyReadiness.detail.source === "string"
      ? copyReadiness.detail.source
      : null;
  const missingDeployRequirements = [
    navigationReadiness.required && navigationReadiness.ready !== true ? "navigation" : null,
    checkoutReadiness.required && checkoutReadiness.ready !== true ? "checkout" : null,
    trackingReadiness.required && trackingReadiness.ready !== true ? "tracking" : null,
    copyReadiness.required && copyReadiness.ready !== true ? "copy" : null,
  ].filter(Boolean) as string[];
  const publishReady = Boolean(funnel.latestPreparedVersionId) && missingDeployRequirements.length === 0;

  const handlePrepareTemplate = async () => {
    try {
      await prepareFunnel.mutateAsync({});
      toast.success("Template prepared");
    } catch (error) {
      console.error("Failed to prepare template:", error);
    }
  };

  const handlePublishSite = async () => {
    try {
      const result = await publishSite.mutateAsync();
      toast.success(`Site published (${result.routeSlug})`);
    } catch (error) {
      console.error("Failed to publish site:", error);
    }
  };

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

              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Page Intent
                </div>
                <div className="mt-1 text-sm font-semibold text-content">
                  {formatPageIntent(funnel.pageIntent)}
                </div>
              </div>

              {funnel.templateImportLabel && (
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    HTML Template
                  </div>
                  <div className="mt-1 text-sm font-semibold text-content">
                    {funnel.templateImportLabel}
                  </div>
                </div>
              )}
            </div>
          </div>

          {funnel.templateImportId && (
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
                <div>
                  <div className="text-sm font-semibold text-content">Template Preparation</div>
                  <div className="text-xs text-content-muted">
                    Generate a prepared site page from the preserved HTML template with campaign copy.
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button onClick={handlePrepareTemplate} disabled={prepareFunnel.isPending}>
                    {prepareFunnel.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Funnel className="mr-2 h-4 w-4" />
                    )}
                    Prepare Template
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handlePublishSite}
                    disabled={!publishReady || publishSite.isPending}
                  >
                    {publishSite.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="mr-2 h-4 w-4" />
                    )}
                    Publish Site
                  </Button>
                </div>
              </div>

              {!publishReady ? (
                <Callout variant="warning" size="sm" className="mt-4" title="Deploy readiness pending">
                  {!funnel.latestPreparedVersionId
                    ? "Prepare the template before publishing this site."
                    : `Resolve these required checks before publishing: ${missingDeployRequirements.join(", ")}.`}
                </Callout>
              ) : null}

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Campaign
                  </div>
                  <div className="mt-1 text-sm font-semibold text-content">
                    {funnel.campaignId ? `${funnel.campaignId.slice(0, 8)}...` : "Not set"}
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Selected Angle
                  </div>
                  <div className="mt-1 text-sm font-semibold text-content">
                    {selectedAngleName || (funnel.selectedAngleId ? `${funnel.selectedAngleId.slice(0, 8)}...` : "Not set")}
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Prepared Page
                  </div>
                  <div className="mt-1 text-sm font-semibold text-content">
                    {funnel.preparedPageSlug ? `/${funnel.preparedPageSlug}` : "Not prepared"}
                  </div>
                  {funnel.preparedPageId ? (
                    <div className="mt-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${funnel.preparedPageId}`)}
                      >
                        <Edit className="mr-1 h-3 w-3" />
                        Open Page
                      </Button>
                    </div>
                  ) : null}
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Last Prepared
                  </div>
                  <div className="mt-1 text-sm font-semibold text-content">
                    {funnel.preparedAt ? new Date(funnel.preparedAt).toLocaleString() : "Never"}
                  </div>
                  <div className="mt-2 text-xs text-content-muted">
                    {funnel.latestPreparedVersionId
                      ? `Version ${funnel.latestPreparedVersionId.slice(0, 8)}...`
                      : "No prepared version yet"}
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Copy Ready
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <Badge tone={copyReady ? "success" : "warning"}>
                      {copyReady ? "Ready" : "Needs configuration"}
                    </Badge>
                    {copySource ? (
                      <Badge tone="neutral">
                        {copySource === "campaign_materialized" ? "Campaign copy" : "Generated for selected angle"}
                      </Badge>
                    ) : null}
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Navigation Ready
                  </div>
                  <div className="mt-1">
                    <Badge tone={navigationReady ? "success" : "warning"}>
                      {navigationReady ? "Ready" : "Needs configuration"}
                    </Badge>
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Checkout Ready
                  </div>
                  <div className="mt-1">
                    <Badge tone={checkoutReady ? "success" : "warning"}>
                      {checkoutReady ? "Ready" : "Needs configuration"}
                    </Badge>
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                    Tracking Ready
                  </div>
                  <div className="mt-1">
                    <Badge tone={trackingReady ? "success" : "warning"}>
                      {trackingReady ? "Ready" : "Needs configuration"}
                    </Badge>
                  </div>
                </div>
              </div>
            </div>
          )}

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
                {[...funnel.steps]
                  .sort((a, b) => a.ordering - b.ordering)
                  .map((step, index) => (
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
