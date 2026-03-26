import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Layers3, Plus, Loader2, Globe, ExternalLink, Download, LayoutTemplate, ArrowRight } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useSites, useSiteFamilies, useCreateSite } from "@/api/sites";
import { useInstantiateSiteTemplate, useSiteTemplates } from "@/api/siteTemplates";
import { useSiteImports } from "@/api/siteImports";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

function formatSiteType(siteType: string | null): string {
  if (!siteType) return "Unknown";
  return siteType
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatCommerceProvider(provider: string | null): string {
  if (!provider) return "None";
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

function formatSiteFamily(family: string | null): string {
  if (!family) return "Unknown";
  return family
    .split("-")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatPageType(pageType: string): string {
  return pageType
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatImportStatus(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "completed") return "success";
  if (["queued", "capturing", "generating", "adapting", "running"].includes(status)) return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

export function SitesPage() {
  const { templateId } = useParams<{ templateId?: string }>();
  const { workspace } = useWorkspace();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: sites = [], isLoading: sitesLoading } = useSites();
  const { data: families = [], isLoading: familiesLoading } = useSiteFamilies();
  const { data: siteTemplates = [], isLoading: templatesLoading } = useSiteTemplates();
  const { data: imports = [], isLoading: importsLoading } = useSiteImports();
  const createSite = useCreateSite();
  const instantiateTemplate = useInstantiateSiteTemplate(templateId || null);

  const routeTab = useMemo<"templates" | "sites" | "imports">(() => {
    if (location.pathname.endsWith("/imports")) return "imports";
    if (location.pathname.includes("/templates")) return "templates";
    return "sites";
  }, [location.pathname]);

  const [activeTab, setActiveTab] = useState<"templates" | "sites" | "imports">(routeTab);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedFamily, setSelectedFamily] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [siteName, setSiteName] = useState("");
  const [siteDescription, setSiteDescription] = useState("");

  useEffect(() => {
    if (routeTab !== activeTab) {
      setActiveTab(routeTab);
    }
  }, [activeTab, routeTab]);

  useEffect(() => {
    if (!templateId) return;
    const template = siteTemplates.find((item) => item.id === templateId);
    if (!template) return;
    setSelectedTemplateId(template.id);
    setSelectedFamily(null);
    setSiteName(`${template.name} Site`);
    setSiteDescription(template.description || "");
    setShowCreateForm(true);
  }, [siteTemplates, templateId]);

  const handleTabChange = (nextTab: "templates" | "sites" | "imports") => {
    setActiveTab(nextTab);
    if (nextTab === "imports") {
      navigate("/workspaces/sites/imports");
      return;
    }
    if (nextTab === "templates") {
      navigate("/workspaces/sites/templates");
      return;
    }
    navigate("/workspaces/sites");
  };

  const handleCreateSite = async () => {
    if (!workspace?.id || (!selectedFamily && !selectedTemplateId) || !siteName.trim()) return;

    try {
      const result = selectedTemplateId
        ? await instantiateTemplate.mutateAsync({
            clientId: workspace.id,
            name: siteName.trim(),
            description: siteDescription.trim() || undefined,
          })
        : await createSite.mutateAsync({
            clientId: workspace.id,
            family: selectedFamily!,
            name: siteName.trim(),
            description: siteDescription.trim() || undefined,
          });
      setShowCreateForm(false);
      setSiteName("");
      setSiteDescription("");
      setSelectedFamily(null);
      setSelectedTemplateId(null);
      navigate(`/workspaces/sites/${("siteId" in result ? result.siteId : result.id)}`);
    } catch (error) {
      console.error("Failed to create site:", error);
    }
  };

  const createPending = createSite.isPending || instantiateTemplate.isPending;
  const createError = createSite.error || instantiateTemplate.error;

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Sites" description="Manage your workspace sites." />
        <EmptyState
          title="No workspace selected"
          description="Select a workspace to manage sites."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sites"
        description="Create and manage sites for your workspace."
      >
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-content-muted">
          <Badge tone="neutral">Workspace: {workspace.name}</Badge>
        </div>
      </PageHeader>

      <Tabs value={activeTab} onValueChange={(v) => handleTabChange(v as typeof activeTab)}>
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="templates" className="flex items-center gap-2">
            <LayoutTemplate className="h-4 w-4" />
            Templates
          </TabsTrigger>
          <TabsTrigger value="sites" className="flex items-center gap-2">
            <Globe className="h-4 w-4" />
            My Sites
            <Badge tone="neutral" className="ml-1">{sites.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="imports" className="flex items-center gap-2">
            <Download className="h-4 w-4" />
            Imports
            <Badge tone="neutral" className="ml-1">{imports.length}</Badge>
          </TabsTrigger>
        </TabsList>

        {/* Templates Tab */}
        <TabsContent value="templates" className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Site Templates</div>
                <div className="text-xs text-content-muted">
                  Choose a starter template to create a new site.
                </div>
              </div>
              <Badge tone="neutral">{families.length + siteTemplates.length} templates</Badge>
            </div>

            {/* Built-in Family Templates */}
            <div className="mt-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-content-muted mb-2">
                Built-in Starters
              </div>
              {familiesLoading ? (
                <div className="py-6 text-sm text-content-muted">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
                  Loading site templates...
                </div>
              ) : (
                <div className="grid gap-3 lg:grid-cols-2">
                  {families.map((family) => (
                    <button
                      key={family.family}
                      type="button"
                      onClick={() => {
                        setSelectedFamily(family.family);
                        setSiteName(`${family.name} Site`);
                        setShowCreateForm(true);
                      }}
                      className={cn(
                        "rounded-xl border px-4 py-4 text-left transition-colors",
                        "border-border bg-surface-2 hover:border-accent/40 hover:bg-surface"
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">
                            {formatCommerceProvider(family.commerceProvider)}
                          </div>
                          <div className="mt-1 text-base font-semibold text-content">{family.name}</div>
                        </div>
                        <Badge tone="accent">{family.pageCount} pages</Badge>
                      </div>
                      <div className="mt-2 text-sm text-content-muted">{family.description}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Workspace Site Templates */}
            {siteTemplates.length > 0 && (
              <div className="mt-6">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted mb-2">
                  Workspace Templates
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  {siteTemplates.map((template) => (
                    <button
                      key={template.id}
                      type="button"
                      onClick={() => navigate(`/workspaces/sites/templates/${template.id}`)}
                      className={cn(
                        "rounded-xl border px-4 py-4 text-left transition-colors",
                        "border-border bg-surface-2 hover:border-accent/40 hover:bg-surface"
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">
                            {formatCommerceProvider(template.commerceProvider)}
                          </div>
                          <div className="mt-1 text-base font-semibold text-content">{template.name}</div>
                        </div>
                        <Badge tone="accent">{template.pageCount} pages</Badge>
                      </div>
                        <div className="mt-2 text-sm text-content-muted">
                          {template.description || `${formatSiteFamily((template as { siteFamily?: string; family?: string }).siteFamily || (template as { family?: string }).family || null)} template`}
                        </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </TabsContent>

        {/* Sites Tab */}
        <TabsContent value="sites" className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Your Sites</div>
                <div className="text-xs text-content-muted">
                  Sites created for this workspace.
                </div>
              </div>
              <Badge tone="neutral">{sites.length} sites</Badge>
            </div>

            {sitesLoading ? (
              <div className="py-6 text-sm text-content-muted">
                <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
                Loading sites...
              </div>
            ) : sites.length === 0 ? (
              <div className="py-6 text-sm text-content-muted">
                No sites created yet. Choose a template from the Templates tab to get started.
              </div>
            ) : (
              <div className="mt-4 space-y-2">
                {sites.map((site) => (
                  <button
                    key={site.id}
                    type="button"
                    onClick={() => navigate(`/workspaces/sites/${site.id}`)}
                    className={cn(
                      "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                      "border-border bg-surface-2 hover:border-accent/40 hover:bg-surface"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold text-content">{site.name}</div>
                        <div className="mt-1 text-xs text-content-muted">
                          {formatSiteFamily(site.siteFamily)} • {formatSiteType(site.siteType)}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone={site.status === "published" ? "success" : "neutral"}>
                          {site.status}
                        </Badge>
                        <ExternalLink className="h-4 w-4 text-content-muted" />
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        {/* Imports Tab */}
        <TabsContent value="imports" className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Site Imports</div>
                <div className="text-xs text-content-muted">
                  Import existing websites to use as templates or add to sites.
                </div>
              </div>
              <Badge tone="neutral">{imports.length} imports</Badge>
            </div>

            {importsLoading ? (
              <div className="py-6 text-sm text-content-muted">
                <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
                Loading imports...
              </div>
            ) : imports.length === 0 ? (
              <div className="py-6 text-sm text-content-muted">
                No imports yet. Start a site import to capture a reference site for this workspace.
              </div>
            ) : (
              <div className="mt-4 space-y-2">
                {imports.map((imp) => (
                  <button
                    key={imp.id}
                    type="button"
                    onClick={() => navigate(`/workspaces/sites/imports/${imp.id}`)}
                    className={cn(
                      "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                      "border-border bg-surface-2 hover:border-accent/40 hover:bg-surface"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold text-content">
                          {imp.title || imp.sourceHostname || imp.sourceUrl}
                        </div>
                        <div className="mt-1 truncate text-xs text-content-muted">{imp.sourceUrl}</div>
                      </div>
                      <Badge tone={formatImportStatus(imp.status)}>{imp.status}</Badge>
                    </div>
                    <div className="mt-2 flex items-center gap-3 text-xs text-content-muted">
                      <span>{imp.suggestedTemplateFamily || "No suggestion"}</span>
                      <span>{new Date(imp.createdAt).toLocaleDateString()}</span>
                      {imp.detectedPageCount && (
                        <span>{imp.detectedPageCount} pages detected</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* Create Site Modal */}
      {showCreateForm && (selectedFamily || selectedTemplateId) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-6">
            <div className="mb-4">
              <div className="text-lg font-semibold text-content">Create New Site</div>
              <div className="mt-1 text-sm text-content-muted">
                Creating a site from the {selectedFamily ? formatSiteFamily(selectedFamily) : "selected"} template.
              </div>
            </div>

            <div className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Site Name</label>
                <Input
                  placeholder="My Site"
                  value={siteName}
                  onChange={(e) => setSiteName(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Description (optional)</label>
                <Input
                  placeholder="A brief description of your site"
                  value={siteDescription}
                  onChange={(e) => setSiteDescription(e.target.value)}
                />
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={handleCreateSite}
                  disabled={!siteName.trim() || createPending}
                  className="flex-1"
                >
                  {createPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Plus className="mr-2 h-4 w-4" />
                      Create Site
                    </>
                  )}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowCreateForm(false);
                    setSelectedFamily(null);
                    setSelectedTemplateId(null);
                    setSiteName("");
                    setSiteDescription("");
                  }}
                  disabled={createPending}
                >
                  Cancel
                </Button>
              </div>

              {createError && (
                <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                  {createError instanceof Error ? createError.message : "Failed to create site. Please try again."}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
