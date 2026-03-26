import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Download, Loader2, Plus, ExternalLink } from "lucide-react";

import { useSiteImports, useSiteImport, useCreateSiteImport, useApplySiteImport } from "@/api/siteImports";
import { useSites } from "@/api/sites";
import { useSiteFamilies } from "@/api/sites";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

function toneForStatus(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (["queued", "capturing", "generating", "adapting", "running"].includes(status)) return "warning";
  return "neutral";
}

export function SiteImportsPage() {
  const navigate = useNavigate();
  const { importId } = useParams<{ importId: string }>();
  const { workspace } = useWorkspace();
  const { data: imports = [], isLoading: importsLoading } = useSiteImports();
  const { data: selectedImport } = useSiteImport(importId || null);
  const { data: sites = [] } = useSites();
  const { data: families = [] } = useSiteFamilies();
  const createImport = useCreateSiteImport();
  const applyImport = useApplySiteImport(importId || null);

  const [sourceUrl, setSourceUrl] = useState("");
  const [siteName, setSiteName] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [selectedSiteId, setSelectedSiteId] = useState("");
  const [selectedFamily, setSelectedFamily] = useState("");

  useEffect(() => {
    if (selectedImport) {
      setSiteName(selectedImport.title || selectedImport.sourceHostname || "Imported Site");
      setTemplateName(selectedImport.title || selectedImport.sourceHostname || "Imported Template");
      setSelectedFamily(selectedImport.suggestedTemplateFamily || families[0]?.family || "medusa-b2b-starter");
    }
  }, [families, selectedImport]);

  const siteOptions = useMemo(
    () => [{ label: "Select target site", value: "" }, ...sites.map((site) => ({ label: site.name, value: site.id }))],
    [sites]
  );
  const familyOptions = useMemo(
    () => families.map((family) => ({ label: family.name, value: family.family })),
    [families]
  );

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site Imports" description="Capture and apply imports inside the Sites workspace." />
        <EmptyState title="No workspace selected" description="Select a workspace to manage site imports." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Site Imports"
        description="Capture reference sites, then apply them as sites, pages, or reusable templates."
      >
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-content-muted">
          <Badge tone="neutral">Workspace: {workspace.name}</Badge>
        </div>
      </PageHeader>

      <div className="rounded-2xl border border-border bg-surface px-4 py-4 space-y-3">
        <div>
          <div className="text-sm font-semibold text-content">Start a new import</div>
          <div className="text-xs text-content-muted">Capture a live site once, then choose an explicit apply action.</div>
        </div>
        <div className="flex gap-2">
          <Input placeholder="https://example.com" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
          <Button
            onClick={async () => {
              const created = await createImport.mutateAsync({ sourceUrl });
              setSourceUrl("");
              navigate(`/workspaces/sites/imports/${created.id}`);
            }}
            disabled={!sourceUrl.trim() || createImport.isPending}
          >
            {createImport.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            <span className="ml-2">Start import</span>
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <div className="rounded-2xl border border-border bg-surface px-4 py-4">
          <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
            <div>
              <div className="text-sm font-semibold text-content">Imports</div>
              <div className="text-xs text-content-muted">Choose an import to review and apply.</div>
            </div>
            <Badge tone="neutral">{imports.length}</Badge>
          </div>
          {importsLoading ? (
            <div className="py-6 text-sm text-content-muted"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Loading imports...</div>
          ) : !imports.length ? (
            <div className="py-6 text-sm text-content-muted">No imports yet.</div>
          ) : (
            <div className="mt-4 space-y-2">
              {imports.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => navigate(`/workspaces/sites/imports/${item.id}`)}
                  className={cn(
                    "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                    importId === item.id ? "border-accent bg-surface" : "border-border bg-surface-2 hover:border-accent/40"
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-content">{item.title || item.sourceHostname || item.sourceUrl}</div>
                      <div className="mt-1 truncate text-xs text-content-muted">{item.sourceUrl}</div>
                    </div>
                    <Badge tone={toneForStatus(item.status)}>{item.status}</Badge>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-border bg-surface px-4 py-4 space-y-4">
          {!selectedImport ? (
            <EmptyState title="Select an import" description="Choose an import from the list to apply it." />
          ) : (
            <>
              <div className="border-b border-border pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-content">{selectedImport.title || selectedImport.sourceHostname || selectedImport.sourceUrl}</div>
                    <div className="mt-1 text-xs text-content-muted">{selectedImport.sourceUrl}</div>
                  </div>
                  <Badge tone={toneForStatus(selectedImport.status)}>{selectedImport.status}</Badge>
                </div>
                <div className="mt-2 text-xs text-content-muted">
                  Suggested family: {selectedImport.suggestedTemplateFamily || "None"}
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-border bg-surface-2 p-4 space-y-3">
                  <div className="text-sm font-semibold text-content">Create site</div>
                  <Input value={siteName} onChange={(e) => setSiteName(e.target.value)} placeholder="Site name" />
                  <Button
                    className="w-full"
                    onClick={async () => {
                      const result = await applyImport.mutateAsync({ action: "create-site", name: siteName });
                      if (result.siteId) navigate(`/workspaces/sites/${result.siteId}`);
                    }}
                    disabled={!siteName.trim() || applyImport.isPending}
                  >
                    Create site
                  </Button>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 p-4 space-y-3">
                  <div className="text-sm font-semibold text-content">Add pages to site</div>
                  <Select value={selectedSiteId} onValueChange={setSelectedSiteId} options={siteOptions} />
                  <Button
                    className="w-full"
                    variant="secondary"
                    onClick={() => applyImport.mutate({ action: "add-pages", targetSiteId: selectedSiteId })}
                    disabled={!selectedSiteId || applyImport.isPending}
                  >
                    Add pages
                  </Button>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 p-4 space-y-3">
                  <div className="text-sm font-semibold text-content">Save as site template</div>
                  <Input value={templateName} onChange={(e) => setTemplateName(e.target.value)} placeholder="Template name" />
                  <Select value={selectedFamily} onValueChange={setSelectedFamily} options={familyOptions} />
                  <Button
                    className="w-full"
                    variant="secondary"
                    onClick={() => applyImport.mutate({ action: "create-site-template", name: templateName, family: selectedFamily })}
                    disabled={!templateName.trim() || !selectedFamily || applyImport.isPending}
                  >
                    Save site template
                  </Button>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 p-4 space-y-3">
                  <div className="text-sm font-semibold text-content">Create page template</div>
                  <div className="text-xs text-content-muted">Use this when you only want a reusable single-page artifact.</div>
                  <Button
                    className="w-full"
                    variant="secondary"
                    onClick={() =>
                      applyImport.mutate({
                        action: "create-page-template",
                        name: templateName || siteName || "Imported Page Template",
                        family: selectedFamily || selectedImport.suggestedTemplateFamily || "sales-pdp",
                        pageType: "product_detail",
                        acceptedSectionIds: [],
                      })
                    }
                    disabled={applyImport.isPending}
                  >
                    Create page template
                  </Button>
                </div>
              </div>

              {applyImport.isError ? (
                <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                  {applyImport.error instanceof Error ? applyImport.error.message : "Failed to apply import."}
                </div>
              ) : null}

              <div className="flex items-center gap-2 text-xs text-content-muted">
                <Download className="h-4 w-4" />
                Canonical site-import actions are available here; legacy storefront template routes remain compatibility-only.
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
