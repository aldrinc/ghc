import { useFunnel, useUpdateFunnel, useCreateFunnelPage, usePublishFunnel, useDisableFunnel, useEnableFunnel, useDuplicateFunnel, useFunnelTemplates, useUpdateFunnelPage } from "@/api/funnels";
import { useApiClient } from "@/api/client";
import { useDesignSystems } from "@/api/designSystems";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogClose, DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

const deployPlanPath = (import.meta.env.VITE_DEPLOY_PLAN_PATH || "").trim();
const deployInstanceName = (import.meta.env.VITE_DEPLOY_INSTANCE_NAME || "").trim();
const deployUpstreamBaseUrl = (import.meta.env.VITE_DEPLOY_UPSTREAM_BASE_URL || "").trim();
const deployUpstreamApiBaseUrl = (import.meta.env.VITE_DEPLOY_UPSTREAM_API_BASE_URL || "").trim();
const deployServerNames = (import.meta.env.VITE_DEPLOY_SERVER_NAMES || "")
  .split(",")
  .map((value: string) => value.trim())
  .filter((value: string) => value.length > 0);

type DeployJobState = {
  jobId: string;
  statusPath: string;
  status: string;
  accessUrl: string | null;
  error: string | null;
};

type DeployJobStatusResponse = {
  id: string;
  status: string;
  access_urls?: string[];
  error?: string | null;
};

export function FunnelDetailPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { funnelId } = useParams();
  const { data: funnel, isLoading } = useFunnel(funnelId);
  const { data: templates } = useFunnelTemplates();
  const { data: designSystems = [] } = useDesignSystems(funnel?.client_id || workspace?.id);
  const updateFunnel = useUpdateFunnel();
  const createPage = useCreateFunnelPage();
  const updatePage = useUpdateFunnelPage();
  const publish = usePublishFunnel();
  const disable = useDisableFunnel();
  const enable = useEnableFunnel();
  const duplicate = useDuplicateFunnel();
  const { get } = useApiClient();

  const [isPageModalOpen, setIsPageModalOpen] = useState(false);
  const [pageName, setPageName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [publishServerNamesInput, setPublishServerNamesInput] = useState(deployServerNames.join(", "));
  const [deployJob, setDeployJob] = useState<DeployJobState | null>(null);

  const pageOptions = useMemo(() => {
    return funnel?.pages?.map((p) => ({ label: `${p.name} (${p.slug})`, value: p.id })) || [];
  }, [funnel?.pages]);

  const statusTone = useMemo(() => {
    return (status: string) => {
      if (status === "published") return "success" as const;
      if (status === "disabled") return "danger" as const;
      return "neutral" as const;
    };
  }, []);

  const handleSetEntryPage = (entryPageId: string) => {
    if (!funnelId) return;
    updateFunnel.mutate({ funnelId, payload: { entryPageId: entryPageId || null } });
  };

  const handleSetDesignSystem = (designSystemId: string) => {
    if (!funnelId) return;
    updateFunnel.mutate({ funnelId, payload: { designSystemId: designSystemId || null } });
  };

  const designSystemOptions = useMemo(() => {
    return [
      { label: "Workspace default", value: "" },
      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
    ];
  }, [designSystems]);

  const handleCreatePage = async (e: FormEvent) => {
    e.preventDefault();
    if (!funnelId || !pageName.trim()) return;
    const resp = await createPage.mutateAsync({ funnelId, name: pageName.trim(), templateId: templateId || undefined });
    setIsPageModalOpen(false);
    setPageName("");
    setTemplateId("");
    const page = resp.page;
    navigate(`/research/funnels/${funnelId}/pages/${page.id}`);
  };

  const publicBase = funnel?.public_id ? `/f/${funnel.public_id}` : null;

  const handlePublish = async (serverNames: string[]) => {
    if (!funnelId || !funnel) return;
    const payload: {
      deploy: {
        workloadName: string;
        createIfMissing: boolean;
        applyPlan: boolean;
        planPath?: string;
        instanceName?: string;
        serverNames?: string[];
        upstreamBaseUrl?: string;
        upstreamApiBaseUrl?: string;
      };
    } = {
      deploy: {
        workloadName: `funnel-${funnel.public_id}`,
        createIfMissing: true,
        applyPlan: true,
      },
    };

    if (deployPlanPath) payload.deploy.planPath = deployPlanPath;
    if (deployInstanceName) payload.deploy.instanceName = deployInstanceName;
    if (serverNames.length > 0) payload.deploy.serverNames = serverNames;
    if (deployUpstreamBaseUrl) payload.deploy.upstreamBaseUrl = deployUpstreamBaseUrl;
    if (deployUpstreamApiBaseUrl) payload.deploy.upstreamApiBaseUrl = deployUpstreamApiBaseUrl;

    const response = await publish.mutateAsync({ funnelId, payload });
    const apply = response.deploy?.apply;
    const jobId = typeof apply?.jobId === "string" ? apply.jobId : "";
    const statusPath = typeof apply?.statusPath === "string" ? apply.statusPath : "";
    if (jobId && statusPath) {
      const initialAccess = Array.isArray(apply?.accessUrls) ? apply.accessUrls[0] || null : null;
      const initialStatus = typeof apply.status === "string" ? apply.status : "queued";
      setDeployJob({
        jobId,
        statusPath,
        status: initialStatus,
        accessUrl: initialAccess,
        error: null,
      });
    }
  };

  const openPublishModal = () => {
    setPublishServerNamesInput(deployServerNames.join(", "));
    setIsPublishModalOpen(true);
  };

  const handlePublishSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const serverNames = Array.from(
      new Set(
        publishServerNamesInput
          .split(",")
          .map((value: string) => value.trim())
          .filter((value: string) => value.length > 0)
      )
    );
    try {
      await handlePublish(serverNames);
      setIsPublishModalOpen(false);
    } catch {
      // toast is handled by the mutation hook
    }
  };

  useEffect(() => {
    if (!deployJob?.statusPath) return;
    if (deployJob.status === "succeeded" || deployJob.status === "failed") return;

    let stopped = false;
    const poll = async () => {
      try {
        const job = await get<DeployJobStatusResponse>(deployJob.statusPath);
        if (stopped) return;
        const accessUrl = Array.isArray(job.access_urls) ? job.access_urls[0] || null : null;
        setDeployJob((current) => {
          if (!current || current.jobId !== job.id) return current;
          return {
            ...current,
            status: job.status,
            accessUrl: accessUrl || current.accessUrl,
            error: job.error || null,
          };
        });
      } catch {
        // Keep polling; publish mutation already surfaces initial errors.
      }
    };

    poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [deployJob?.jobId, deployJob?.status, deployJob?.statusPath, get]);

  return (
    <div className="space-y-4">
      <PageHeader
        title={funnel?.name || "Funnel"}
        description={workspace ? `Workspace: ${workspace.name}` : "Funnel builder"}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setIsPageModalOpen(true)} disabled={!funnelId || !funnel}>
              New page
            </Button>
            {deployJob?.status === "succeeded" && deployJob.accessUrl ? (
              <Button variant="secondary" size="sm" asChild>
                <a href={deployJob.accessUrl} target="_blank" rel="noreferrer">
                  Open Deployed Page
                </a>
              </Button>
            ) : null}
            <Button
              size="sm"
              onClick={openPublishModal}
              disabled={!funnel?.canPublish || publish.isPending}
            >
              {publish.isPending ? "Publishing…" : "Publish + Deploy"}
            </Button>
          </div>
        }
      />

      {isLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted">Loading…</div>
      ) : !funnel ? (
        <div className="ds-card ds-card--md text-sm text-content-muted">Funnel not found.</div>
      ) : (
        <>
          {deployJob ? (
            <div className="ds-card ds-card--md text-xs text-content-muted">
              Deploy job <span className="font-mono">{deployJob.jobId}</span>:{" "}
              <span className="font-semibold text-content">{deployJob.status}</span>
              {deployJob.error ? <span className="ml-2 text-danger">{deployJob.error}</span> : null}
            </div>
          ) : null}
          <div className="ds-card ds-card--md space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge tone={statusTone(funnel.status)}>{funnel.status}</Badge>
                {funnel.campaign_id ? <Badge tone="neutral">Campaign-linked</Badge> : <Badge tone="neutral">No campaign</Badge>}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    if (!publicBase) return;
                    navigator.clipboard.writeText(window.location.origin + publicBase);
                  }}
                  disabled={!publicBase}
                >
                  Copy share link
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => funnelId && duplicate.mutate({ funnelId })}
                  disabled={!funnelId || duplicate.isPending}
                >
                  {duplicate.isPending ? "Duplicating…" : "Duplicate"}
                </Button>
                {funnel.status === "disabled" ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => funnelId && enable.mutate(funnelId)}
                    disabled={!funnelId || enable.isPending}
                  >
                    Enable
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => funnelId && disable.mutate(funnelId)}
                    disabled={!funnelId || disable.isPending}
                  >
                    Disable
                  </Button>
                )}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <div className="space-y-1">
                <div className="text-xs font-semibold text-content">Entry page</div>
                <Select
                  value={funnel.entry_page_id || ""}
                  onValueChange={handleSetEntryPage}
                  options={[{ label: "Select entry page", value: "" }, ...pageOptions]}
                  disabled={!funnel.pages.length || updateFunnel.isPending}
                />
              </div>
              <div className="space-y-1">
                <div className="text-xs font-semibold text-content">Design system</div>
                <Select
                  value={funnel.design_system_id || ""}
                  onValueChange={handleSetDesignSystem}
                  options={designSystemOptions}
                  disabled={updateFunnel.isPending}
                />
              </div>
              <div className="space-y-1">
                <div className="text-xs font-semibold text-content">Public link</div>
                <div className="rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-xs text-content">
                  {publicBase ? publicBase : "—"}
                </div>
              </div>
            </div>
          </div>

          <div className="ds-card ds-card--md p-0 shadow-none">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <div className="text-sm font-semibold text-content">Pages</div>
                <div className="text-xs text-content-muted">{funnel.pages.length} pages</div>
              </div>
              <div className="text-xs text-content-muted">Set next page wiring, approve each page, then publish</div>
            </div>
            <ul className="divide-y divide-border">
              {funnel.pages.map((page) => {
                const isApproved = Boolean(page.latestApprovedVersionId);
                const nextPageOptions = [
                  { label: "No next page", value: "" },
                  ...funnel.pages
                    .filter((candidate) => candidate.id !== page.id)
                    .map((candidate) => ({
                      label: `${candidate.name} (${candidate.slug})`,
                      value: candidate.id,
                    })),
                ];
                return (
                  <li key={page.id} className="px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <Link
                            to={`/research/funnels/${funnel.id}/pages/${page.id}`}
                            className="font-semibold text-content hover:underline"
                          >
                            {page.name}
                          </Link>
                          <Badge tone={isApproved ? "success" : "warning"}>{isApproved ? "approved" : "needs approval"}</Badge>
                        </div>
                        <div className="text-xs text-content-muted">
                          Slug: <span className="font-mono">{page.slug}</span>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="min-w-[220px] space-y-1">
                          <div className="text-[10px] font-semibold uppercase text-content-muted">Next page</div>
                          <Select
                            value={page.next_page_id || ""}
                            onValueChange={(nextPageId) => {
                              if (!funnelId) return;
                              updatePage.mutate({
                                funnelId,
                                pageId: page.id,
                                payload: { nextPageId: nextPageId || null },
                              });
                            }}
                            options={nextPageOptions}
                            disabled={updatePage.isPending}
                          />
                        </div>
                        {publicBase ? (
                          <Link to={`${publicBase}/${page.slug}`} target="_blank" className="text-xs text-content-muted hover:underline">
                            Open public
                          </Link>
                        ) : null}
                        <Button variant="secondary" size="sm" asChild>
                          <Link to={`/research/funnels/${funnel.id}/pages/${page.id}`}>Edit</Link>
                        </Button>
                      </div>
                    </div>
                  </li>
                );
              })}
              {!funnel.pages.length ? (
                <li className="px-4 py-3 text-sm text-content-muted">No pages yet. Create one to start.</li>
              ) : null}
            </ul>
          </div>
        </>
      )}

      <DialogRoot open={isPageModalOpen} onOpenChange={setIsPageModalOpen}>
        <DialogContent>
          <DialogTitle>New page</DialogTitle>
          <DialogDescription>Add a page to this funnel. You can wire CTAs to other pages after saving.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreatePage}>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Page name</label>
              <Input
                placeholder="e.g. Landing page"
                value={pageName}
                onChange={(e) => setPageName(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Template</label>
              <Select
                value={templateId}
                onValueChange={setTemplateId}
                options={[
                  { label: "Blank page", value: "" },
                  ...(templates || []).map((tpl) => ({
                    label: tpl.name,
                    value: tpl.id,
                  })),
                ]}
              />
              {templateId ? (
                <div className="text-xs text-content-muted">
                  {(templates || []).find((tpl) => tpl.id === templateId)?.description || "Template selected"}
                </div>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={!pageName.trim() || createPage.isPending}>
                {createPage.isPending ? "Creating…" : "Create page"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>

      <DialogRoot open={isPublishModalOpen} onOpenChange={setIsPublishModalOpen}>
        <DialogContent>
          <DialogTitle>Publish + Deploy</DialogTitle>
          <DialogDescription>
            Enter one or more domains to bind this deploy (comma separated). Leave blank for catch-all HTTP.
          </DialogDescription>
          <form className="space-y-3" onSubmit={handlePublishSubmit}>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Deploy domains</label>
              <Input
                placeholder="landing.example.com, www.landing.example.com"
                value={publishServerNamesInput}
                onChange={(e) => setPublishServerNamesInput(e.target.value)}
              />
              <div className="text-xs text-content-muted">
                Empty input deploys without host-specific TLS (HTTP catch-all).
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary" disabled={publish.isPending}>
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={publish.isPending}>
                {publish.isPending ? "Publishing…" : "Publish"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
