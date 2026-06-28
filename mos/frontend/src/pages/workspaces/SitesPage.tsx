import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Plus, Loader2, Globe, ExternalLink, Download, LayoutTemplate } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useSites, useSiteFamilies, useCreateSite, type SiteThemeBindingMode } from "@/api/sites";
import { useInstantiateSiteTemplate, useSiteTemplates } from "@/api/siteTemplates";
import { useSiteImports } from "@/api/siteImports";
import { useDesignSystems } from "@/api/designSystems";
import { useProductContext } from "@/contexts/ProductContext";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogContent, DialogRoot, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { Callout } from "@/components/ui/callout";
import { cn } from "@/lib/utils";
import {
  formatSiteType,
  formatCommerceProvider,
  formatSiteFamily,
  formatImportStatus,
} from "@/lib/siteFormatters";

/* ------------------------------------------------------------------ */
/*  Skeleton placeholders                                              */
/* ------------------------------------------------------------------ */

function TemplateCardSkeleton() {
  return (
    <div className="ds-card ds-card--sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-5 w-36" />
        </div>
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <Skeleton className="mt-3 h-4 w-full" />
    </div>
  );
}

function SiteRowSkeleton() {
  return (
    <div className="ds-card ds-card--sm">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-2">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-56" />
        </div>
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section Card – replaces the repeated section wrapper pattern       */
/* ------------------------------------------------------------------ */

function SectionCard({
  title,
  description,
  count,
  countLabel,
  children,
}: {
  title: string;
  description: string;
  count?: number;
  countLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="ds-section-card">
      <div className="ds-section-card__header">
        <div>
          <div className="text-sm font-semibold text-content">{title}</div>
          <div className="text-xs text-content-muted">{description}</div>
        </div>
        {count !== undefined && (
          <Badge tone="neutral">{count} {countLabel ?? "items"}</Badge>
        )}
      </div>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function SitesPage() {
  const { templateId } = useParams<{ templateId?: string }>();
  const { workspace } = useWorkspace();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: sites = [], isLoading: sitesLoading } = useSites();
  const { data: families = [], isLoading: familiesLoading } = useSiteFamilies();
  const { data: siteTemplates = [] } = useSiteTemplates();
  const { data: imports = [], isLoading: importsLoading } = useSiteImports();
  const { data: designSystems = [] } = useDesignSystems(workspace?.id);
  const { product: activeWorkspaceProduct, products: workspaceProducts, isLoading: productsLoading } = useProductContext();
  const createSite = useCreateSite();
  const instantiateTemplate = useInstantiateSiteTemplate(templateId || null);

  /* ---- routing-driven tab ---- */
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
  const [selectedProductId, setSelectedProductId] = useState("");

  // Theme binding state
  const [themeBindingMode, setThemeBindingMode] = useState<SiteThemeBindingMode>("standalone");
  const [selectedDesignSystemId, setSelectedDesignSystemId] = useState<string>("");

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
    setSelectedProductId(activeWorkspaceProduct?.id || "");
    setThemeBindingMode("standalone");
    setSelectedDesignSystemId("");
    setShowCreateForm(true);
  }, [activeWorkspaceProduct?.id, siteTemplates, templateId]);

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

  const resetCreateForm = () => {
    setShowCreateForm(false);
    setSelectedFamily(null);
    setSelectedTemplateId(null);
    setSiteName("");
    setSiteDescription("");
    setSelectedProductId("");
    setThemeBindingMode("standalone");
    setSelectedDesignSystemId("");
  };

  const handleCreateSite = async () => {
    if (!workspace?.id || (!selectedFamily && !selectedTemplateId) || !siteName.trim()) return;

    try {
      const result = selectedTemplateId
        ? await instantiateTemplate.mutateAsync({
            clientId: workspace.id,
            name: siteName.trim(),
            description: siteDescription.trim() || undefined,
            productId: selectedProductId || undefined,
            themeBindingMode,
            designSystemId: themeBindingMode === "design_system" ? selectedDesignSystemId || undefined : undefined,
          })
        : await createSite.mutateAsync({
            clientId: workspace.id,
            family: selectedFamily!,
            name: siteName.trim(),
            description: siteDescription.trim() || undefined,
            productId: selectedProductId || undefined,
            themeBindingMode,
            designSystemId: themeBindingMode === "design_system" ? selectedDesignSystemId || undefined : undefined,
          });
      resetCreateForm();
      toast.success("Site created");
      navigate(`/workspaces/sites/${("siteId" in result ? result.siteId : result.id)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create site. Please try again.");
    }
  };

  const createPending = createSite.isPending || instantiateTemplate.isPending;

  const designSystemOptions = useMemo(() => [
    { label: "Select a design system", value: "" },
    ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
  ], [designSystems]);
  const productOptions = useMemo(() => [
    { label: productsLoading ? "Loading products..." : "No default product", value: "" },
    ...workspaceProducts.map((product) => ({ label: product.title, value: product.id })),
  ], [productsLoading, workspaceProducts]);

  const themeModeOptions = [
    { label: "Standalone (no theme)", value: "standalone", description: "Use generic styling without brand tokens" },
    { label: "Use workspace brand", value: "workspace_default", description: "Inherit the workspace default design system" },
    { label: "Use specific design system", value: "design_system", description: "Select a design system to apply" },
  ];

  /* ---- early return: no workspace ---- */
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
      />

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

        {/* ---- Templates Tab ---- */}
        <TabsContent value="templates" className="space-y-4">
          <SectionCard
            title="Site Templates"
            description="Choose a starter template to create a new site."
            count={families.length + siteTemplates.length}
            countLabel="templates"
          >
            {/* Built-in Family Templates */}
            <div>
              <div className="text-overline mb-2">Built-in Starters</div>
              {familiesLoading ? (
                <div className="grid gap-3 lg:grid-cols-2">
                  <TemplateCardSkeleton />
                  <TemplateCardSkeleton />
                </div>
              ) : (
                <div className="grid gap-3 lg:grid-cols-2">
                  {families.map((family) => (
                    <button
                      key={family.family}
                      type="button"
                      aria-label={`Select ${family.name} template`}
                      onClick={() => {
                        setSelectedFamily(family.family);
                        setSiteName(`${family.name} Site`);
                        setSelectedProductId(activeWorkspaceProduct?.id || "");
                        setThemeBindingMode("standalone");
                        setSelectedDesignSystemId("");
                        setShowCreateForm(true);
                      }}
                      className={cn(
                        "ds-card ds-card--sm text-left transition-colors",
                        "hover:border-accent/40 hover:bg-surface"
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-content">{family.name}</div>
                        <div className="flex items-center gap-1.5">
                          <Badge tone="neutral">{formatCommerceProvider(family.commerceProvider)}</Badge>
                          <Badge tone="accent">{family.pageCount} pages</Badge>
                        </div>
                      </div>
                      <div className="mt-1.5 text-sm text-content-muted">{family.description}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Workspace Site Templates */}
            {siteTemplates.length > 0 && (
              <div className="mt-6">
                <div className="text-overline mb-2">Workspace Templates</div>
                <div className="grid gap-3 lg:grid-cols-2">
                  {siteTemplates.map((template) => (
                    <button
                      key={template.id}
                      type="button"
                      aria-label={`Select ${template.name} template`}
                      onClick={() => navigate(`/workspaces/sites/templates/${template.id}`)}
                      className={cn(
                        "ds-card ds-card--sm text-left transition-colors",
                        "hover:border-accent/40 hover:bg-surface"
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-content">{template.name}</div>
                        <div className="flex items-center gap-1.5">
                          <Badge tone="neutral">{formatCommerceProvider(template.commerceProvider)}</Badge>
                          <Badge tone="accent">{template.pageCount} pages</Badge>
                        </div>
                      </div>
                      <div className="mt-1.5 text-sm text-content-muted">
                        {template.description || `${formatSiteFamily((template as { siteFamily?: string; family?: string }).siteFamily || (template as { family?: string }).family || null)} template`}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </SectionCard>
        </TabsContent>

        {/* ---- Sites Tab ---- */}
        <TabsContent value="sites" className="space-y-4">
          <SectionCard
            title="Your Sites"
            description="Sites created for this workspace."
            count={sites.length}
            countLabel="sites"
          >
            {sitesLoading ? (
              <div className="space-y-2">
                <SiteRowSkeleton />
                <SiteRowSkeleton />
                <SiteRowSkeleton />
              </div>
            ) : sites.length === 0 ? (
              <EmptyState
                title="No sites yet"
                description="Choose a template from the Templates tab to get started."
                actions={
                  <Button size="sm" variant="outline" onClick={() => handleTabChange("templates")}>
                    <LayoutTemplate className="mr-2 h-4 w-4" />
                    Browse Templates
                  </Button>
                }
              />
            ) : (
              <div className="space-y-2">
                {sites.map((site) => (
                  <button
                    key={site.id}
                    type="button"
                    aria-label={`View site: ${site.name}`}
                    onClick={() => navigate(`/workspaces/sites/${site.id}`)}
                    className={cn(
                      "ds-card ds-card--sm w-full text-left transition-colors",
                      "hover:border-accent/40 hover:bg-surface"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold text-content">{site.name}</div>
                        <div className="mt-1 text-xs text-content-muted">
                          {formatSiteFamily(site.siteFamily)} • {formatSiteType(site.siteType)}
                          {site.themeBindingMode && (
                            <span> • Theme: {site.themeBindingMode === "standalone" ? "Standalone" :
                              site.themeBindingMode === "workspace_default" ? "Workspace brand" : "Design system"}</span>
                          )}
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
          </SectionCard>
        </TabsContent>

        {/* ---- Imports Tab ---- */}
        <TabsContent value="imports" className="space-y-4">
          <SectionCard
            title="Site Imports"
            description="Import existing websites to use as templates or add to sites."
            count={imports.length}
            countLabel="imports"
          >
            {importsLoading ? (
              <div className="space-y-2">
                <SiteRowSkeleton />
                <SiteRowSkeleton />
              </div>
            ) : imports.length === 0 ? (
              <EmptyState
                title="No imports yet"
                description="Start a site import to capture a reference site for this workspace."
              />
            ) : (
              <div className="space-y-2">
                {imports.map((imp) => (
                  <button
                    key={imp.id}
                    type="button"
                    aria-label={`View import: ${imp.title || imp.sourceHostname || imp.sourceUrl}`}
                    onClick={() => navigate(`/workspaces/sites/imports/${imp.id}`)}
                    className={cn(
                      "ds-card ds-card--sm w-full text-left transition-colors",
                      "hover:border-accent/40 hover:bg-surface"
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
          </SectionCard>
        </TabsContent>
      </Tabs>

      {/* ---- Create Site Dialog ---- */}
      <DialogRoot open={showCreateForm && !!(selectedFamily || selectedTemplateId)} onOpenChange={(open) => { if (!open) resetCreateForm(); }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <div className="space-y-1">
            <DialogTitle>Create New Site</DialogTitle>
            <DialogDescription>
              Creating a site from the {selectedFamily ? formatSiteFamily(selectedFamily) : "selected"} template.
            </DialogDescription>
          </div>

          <div className="mt-4 space-y-5">
            {/* Site Details */}
            <div className="space-y-3">
              <FormField label="Site Name" required>
                <Input
                  placeholder="My Site"
                  value={siteName}
                  onChange={(e) => setSiteName(e.target.value)}
                />
              </FormField>

              <FormField label="Description" helper="Optional — a brief description of your site.">
                <Input
                  placeholder="A brief description of your site"
                  value={siteDescription}
                  onChange={(e) => setSiteDescription(e.target.value)}
                />
              </FormField>

              <FormField
                label="Default Product"
                helper="Sets the site's default product context. You can still add page-level product bindings later."
              >
                <Select
                  options={productOptions}
                  value={selectedProductId}
                  onValueChange={setSelectedProductId}
                  disabled={productsLoading}
                />
              </FormField>
            </div>

            {/* Theme Section */}
            <div className="space-y-3 border-t border-border pt-4">
              <div className="text-overline">Theme</div>

              <div className="space-y-2">
                {themeModeOptions.map((option) => (
                  <label
                    key={option.value}
                    className={cn(
                      "flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors",
                      themeBindingMode === option.value
                        ? "border-accent bg-accent/5"
                        : "border-border bg-surface-2 hover:border-accent/40"
                    )}
                  >
                    <input
                      type="radio"
                      name="themeBindingMode"
                      value={option.value}
                      checked={themeBindingMode === option.value}
                      onChange={(e) => setThemeBindingMode(e.target.value as SiteThemeBindingMode)}
                      className="mt-0.5"
                    />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-content">{option.label}</div>
                      <div className="text-xs text-content-muted">{option.description}</div>
                    </div>
                  </label>
                ))}
              </div>

              {/* Design System Picker */}
              {themeBindingMode === "design_system" && (
                <FormField label="Design System">
                  <Select
                    options={designSystemOptions}
                    value={selectedDesignSystemId}
                    onValueChange={setSelectedDesignSystemId}
                  />
                  {designSystems.length === 0 && (
                    <Callout variant="warning" size="sm" className="mt-2">
                      No design systems available. Create one in the Brand Design System page first.
                    </Callout>
                  )}
                </FormField>
              )}
            </div>

            {/* Actions — Cancel left, Primary right */}
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                variant="outline"
                onClick={resetCreateForm}
                disabled={createPending}
              >
                Cancel
              </Button>
              <Button
                onClick={handleCreateSite}
                disabled={!siteName.trim() || createPending || (themeBindingMode === "design_system" && !selectedDesignSystemId)}
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
            </div>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
