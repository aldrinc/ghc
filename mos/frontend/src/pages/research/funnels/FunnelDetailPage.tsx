import { useFunnel, useUpdateFunnel, useCreateFunnelPage, usePublishFunnel, useDisableFunnel, useEnableFunnel, useDuplicateFunnel, useFunnelTemplates, useUpdateFunnelPage } from "@/api/funnels";
import { useApiClient } from "@/api/client";
import { useDeployWorkloadDomains } from "@/api/deploy";
import { useDesignSystems } from "@/api/designSystems";
import { useProduct } from "@/api/products";
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

type PatchWorkloadResponse = {
  status: string;
  base_plan_path: string;
  updated_plan_path: string;
  workload_name: string;
  updated_count: number;
};

type DeployJobState = {
  jobId: string;
  statusPath: string;
  status: string;
  accessUrl: string | null;
  publicationId: string | null;
  error: string | null;
};

type DeployJobStatusResponse = {
  id: string;
  status: string;
  access_urls?: string[];
  result?: {
    publicationId?: string | null;
  } | null;
  error?: string | null;
};

function artifactForTemplate(templateId: string | null | undefined): "presales" | "sales" | null {
  if (templateId === "pre-sales-listicle") return "presales";
  if (templateId === "sales-pdp") return "sales";
  return null;
}

export function FunnelDetailPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { funnelId } = useParams();
  const { data: funnel, isLoading } = useFunnel(funnelId);
  const { data: funnelProduct } = useProduct(funnel?.product_id || undefined);
  const { data: templates } = useFunnelTemplates();
  const { data: designSystems = [] } = useDesignSystems(funnel?.client_id || workspace?.id);
  const updateFunnel = useUpdateFunnel();
  const createPage = useCreateFunnelPage();
  const updatePage = useUpdateFunnelPage();
  const publish = usePublishFunnel();
  const disable = useDisableFunnel();
  const enable = useEnableFunnel();
  const duplicate = useDuplicateFunnel();
  const { get, post } = useApiClient();

  const [isPageModalOpen, setIsPageModalOpen] = useState(false);
  const [pageName, setPageName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [deployJob, setDeployJob] = useState<DeployJobState | null>(null);
  const [isEditingDeployDomains, setIsEditingDeployDomains] = useState(false);
  const [deployDomainsDraft, setDeployDomainsDraft] = useState<string[]>([]);
  const [deployDomainsInput, setDeployDomainsInput] = useState("");
  const [deployDomainsSaveError, setDeployDomainsSaveError] = useState<string | null>(null);
  const [isSavingDeployDomains, setIsSavingDeployDomains] = useState(false);

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

  const handleSetSelectedOffer = (selectedOfferId: string) => {
    if (!funnelId) return;
    updateFunnel.mutate({ funnelId, payload: { selectedOfferId: selectedOfferId || null } });
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

  const publicBase = funnel?.route_slug ? `/f/${funnel.route_slug}` : null;
  const mosPreviewUrl = publicBase ? `${window.location.origin}${publicBase}` : null;
  const deployWorkloadName = funnel?.product_id ? `product-funnels-${funnel.product_id}` : undefined;
  const entryArtifact = useMemo(() => {
    if (!funnel?.entry_page_id || !funnel.pages?.length) return null;
    const entryPage = funnel.pages.find((page) => page.id === funnel.entry_page_id);
    return artifactForTemplate(entryPage?.template_id);
  }, [funnel?.entry_page_id, funnel?.pages]);

  const deployDomains = useDeployWorkloadDomains({
    workloadName: deployWorkloadName,
    planPath: deployPlanPath || undefined,
    instanceName: deployInstanceName || undefined,
  });

  const deployedPageUrl = useMemo(() => {
    if (!funnel?.route_slug || !entryArtifact) return null;

    const accessCandidate =
      (deployJob?.accessUrl || "").trim() ||
      (() => {
        const host = deployDomains.data?.server_names?.[0];
        if (!host) return "";
        const scheme = deployDomains.data?.https ? "https" : "http";
        return `${scheme}://${host}/`;
      })();

    const baseUrl = accessCandidate || `${window.location.origin}/`;
    const normalizedBase = baseUrl.replace(/\/+$/, "");
    return `${normalizedBase}/${encodeURIComponent(funnel.route_slug)}/${encodeURIComponent(entryArtifact)}`;
  }, [
    deployDomains.data?.https,
    deployDomains.data?.server_names,
    deployJob?.accessUrl,
    entryArtifact,
    funnel?.route_slug,
  ]);

  const normalizeDeployDomainList = (values: string[]): string[] => {
    const out: string[] = [];
    const seen = new Set<string>();
    for (const raw of values) {
      const token = (raw || "").trim().toLowerCase();
      if (!token || seen.has(token)) continue;
      seen.add(token);
      out.push(token);
    }
    return out;
  };

  const parseDeployDomains = (raw: string): string[] => {
    const tokens = raw
      .split(/[,\s]+/g)
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);

    const out: string[] = [];
    const seen = new Set<string>();
    for (const token of tokens) {
      if (token.includes("://") || token.includes("/") || token.includes("?") || token.includes("#")) {
        throw new Error("Domains must be hostnames only (e.g. example.com), not full URLs.");
      }
      if (seen.has(token)) continue;
      seen.add(token);
      out.push(token);
    }
    return out;
  };

  const startEditingDeployDomains = () => {
    if (!deployDomains.data?.workload_found) return;
    setDeployDomainsDraft(normalizeDeployDomainList(deployDomains.data.server_names || []));
    setDeployDomainsInput("");
    setDeployDomainsSaveError(null);
    setIsEditingDeployDomains(true);
  };

  const cancelEditingDeployDomains = () => {
    setIsEditingDeployDomains(false);
    setDeployDomainsDraft([]);
    setDeployDomainsInput("");
    setDeployDomainsSaveError(null);
  };

  const addDeployDomainsFromInput = () => {
    setDeployDomainsSaveError(null);
    try {
      const next = parseDeployDomains(deployDomainsInput);
      if (!next.length) return;
      setDeployDomainsDraft((current) => {
        const merged = [...current];
        const seen = new Set(current.map((d) => d.toLowerCase()));
        for (const item of next) {
          if (seen.has(item)) continue;
          seen.add(item);
          merged.push(item);
        }
        return merged;
      });
      setDeployDomainsInput("");
    } catch (err) {
      setDeployDomainsSaveError(err instanceof Error ? err.message : "Invalid deploy domains.");
    }
  };

  const removeDeployDomain = (hostname: string) => {
    setDeployDomainsDraft((current) => current.filter((d) => d !== hostname));
  };

  const saveDeployDomains = async () => {
    setDeployDomainsSaveError(null);
    if (!deployWorkloadName) {
      setDeployDomainsSaveError("Deploy workload name is missing for this funnel.");
      return;
    }
    const planPath = (deployDomains.data?.plan_path || "").trim();
    if (!planPath) {
      setDeployDomainsSaveError("No deploy plan is available to update.");
      return;
    }

    setIsSavingDeployDomains(true);
    try {
      const params = new URLSearchParams();
      params.set("plan_path", planPath);
      if (deployInstanceName) params.set("instance_name", deployInstanceName);
      params.set("create_if_missing", "false");
      params.set("in_place", "true");

      await post<PatchWorkloadResponse>(`/deploy/plans/workloads?${params.toString()}`, {
        name: deployWorkloadName,
        service_config: {
          server_names: deployDomainsDraft,
          https: deployDomainsDraft.length > 0,
        },
      });

      setIsEditingDeployDomains(false);
      void deployDomains.refetch();
    } catch (err) {
      setDeployDomainsSaveError(
        typeof (err as { message?: unknown })?.message === "string"
          ? String((err as { message?: unknown }).message)
          : "Failed to update deploy domains.",
      );
    } finally {
      setIsSavingDeployDomains(false);
    }
  };

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
        workloadName: `product-funnels-${funnel.product_id || funnel.id}`,
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
    void deployDomains.refetch();
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
        publicationId: typeof response.publicationId === "string" ? response.publicationId : null,
        error: null,
      });
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
        const publicationId = typeof job.result?.publicationId === "string" ? job.result.publicationId : null;
        setDeployJob((current) => {
          if (!current || current.jobId !== job.id) return current;
          return {
            ...current,
            status: job.status,
            accessUrl: accessUrl || current.accessUrl,
            publicationId: publicationId || current.publicationId,
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
            {funnel?.status === "published" && deployedPageUrl ? (
              <Button variant="secondary" size="sm" asChild>
                <a href={deployedPageUrl} target="_blank" rel="noreferrer">
                  Open Deployed Page
                </a>
              </Button>
            ) : null}
            {deployJob?.publicationId && mosPreviewUrl ? (
              <Button variant="secondary" size="sm" asChild>
                <a href={mosPreviewUrl} target="_blank" rel="noreferrer">
                  Open In MOS
                </a>
              </Button>
            ) : null}
            <Button
              size="sm"
              onClick={() => void handlePublish(deployDomains.data?.server_names || [])}
              disabled={!funnel?.canPublish || publish.isPending || deployDomains.isLoading}
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

            <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
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
                <div className="text-xs font-semibold text-content">Selected offer</div>
                <Select
                  value={funnel.selected_offer_id || ""}
                  onValueChange={handleSetSelectedOffer}
                  options={[
                    { label: funnelProduct?.offers?.length ? "No selected offer" : "No offers available", value: "" },
                    ...((funnelProduct?.offers || []).map((offer) => ({ label: offer.name, value: offer.id }))),
                  ]}
                  disabled={updateFunnel.isPending || !(funnelProduct?.offers?.length)}
                />
              </div>
              <div className="space-y-1">
                <div className="text-xs font-semibold text-content">Public link</div>
                <div className="flex h-10 items-center rounded-md border border-border bg-surface-2 px-3 font-mono text-xs text-content">
                  <span className="truncate">{publicBase ? publicBase : "—"}</span>
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-xs font-semibold text-content">Deploy domains</div>
                <div className="rounded-md border border-border bg-surface-2 text-xs text-content">
                  {deployDomains.data?.workload_found && isEditingDeployDomains ? (
                    <div className="px-3 py-2 space-y-2">
                      <div className="flex flex-wrap gap-1">
                        {deployDomainsDraft.length ? (
                          deployDomainsDraft.map((hostname) => (
                            <span
                              key={hostname}
                              className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5 font-mono text-[11px] text-content"
                            >
                              {hostname}
                              <button
                                type="button"
                                onClick={() => removeDeployDomain(hostname)}
                                className="ml-1 rounded-full px-1 text-content-muted hover:bg-surface-3 hover:text-content"
                                aria-label={`Remove ${hostname}`}
                              >
                                x
                              </button>
                            </span>
                          ))
                        ) : (
                          <span className="text-content-muted">No domains</span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <Input
                          value={deployDomainsInput}
                          onChange={(e) => setDeployDomainsInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key !== "Enter") return;
                            e.preventDefault();
                            addDeployDomainsFromInput();
                          }}
                          placeholder="Add domain(s), comma or space separated"
                          className="h-8 min-w-[220px] flex-1 font-mono text-[11px]"
                        />
                        <Button type="button" size="sm" variant="secondary" onClick={addDeployDomainsFromInput} disabled={!deployDomainsInput.trim()}>
                          Add
                        </Button>
                      </div>

                      {deployDomainsSaveError ? <div className="text-xs text-danger">{deployDomainsSaveError}</div> : null}

                      <div className="flex items-center justify-end gap-2">
                        <Button type="button" size="sm" variant="secondary" onClick={cancelEditingDeployDomains} disabled={isSavingDeployDomains}>
                          Cancel
                        </Button>
                        <Button type="button" size="sm" onClick={() => void saveDeployDomains()} disabled={isSavingDeployDomains}>
                          {isSavingDeployDomains ? "Saving…" : "Save"}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex h-10 items-center justify-between gap-2 overflow-hidden px-3">
                      {deployDomains.isLoading ? (
                        <span className="truncate text-content-muted">Loading…</span>
                      ) : deployDomains.isError ? (
                        <span className="truncate text-danger">
                          {(deployDomains.error as { message?: string })?.message || "Unable to load deploy domains."}
                        </span>
                      ) : deployDomains.data?.workload_found ? (
                        <>
                          {deployDomains.data.server_names.length ? (
                            <div className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
                              {deployDomains.data.server_names.map((hostname) => (
                                <a
                                  key={hostname}
                                  href={`${deployDomains.data?.https ? "https" : "http"}://${hostname}/`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-block max-w-[180px] truncate rounded-full border border-border bg-surface px-2 py-0.5 font-mono text-[11px] text-content hover:bg-surface-3"
                                >
                                  {hostname}
                                </a>
                              ))}
                            </div>
                          ) : (
                            <span className="truncate text-content-muted">—</span>
                          )}
                          <Button
                            type="button"
                            size="xs"
                            variant="secondary"
                            onClick={startEditingDeployDomains}
                            className="shrink-0"
                          >
                            Edit
                          </Button>
                        </>
                      ) : (
                        <span className="truncate text-content-muted">Not in plan yet</span>
                      )}
                    </div>
                  )}
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
              <div className="text-xs text-content-muted">Set next page wiring, then publish</div>
            </div>
            <ul className="divide-y divide-border">
              {funnel.pages.map((page) => {
                const hasDraft = Boolean(page.latestDraftVersionId);
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
                          <Badge tone={hasDraft ? "neutral" : "warning"}>{hasDraft ? "draft" : "no saved version"}</Badge>
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
    </div>
  );
}
