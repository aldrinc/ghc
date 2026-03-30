import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Download,
  Globe,
  RefreshCw,
} from "lucide-react";

import {
  useCreateSiteImport,
  useCreateSiteImportFromArchive,
  useSiteImports,
  useTemplateVariants,
} from "@/api/storefrontTemplates";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { readQueryError } from "@/components/import/importUtils";

import { ImportListSidebar } from "@/components/import/ImportListSidebar";
import { ImportDetailPanel } from "@/components/import/ImportDetailPanel";
import { VariantMutationPanel } from "@/components/import/VariantMutationPanel";
import { GovernancePanel } from "@/components/import/GovernancePanel";
import { formatPageType } from "@/lib/siteFormatters";

const importPageHintOptions = [
  { label: "No page hint", value: "" },
  { label: "Home", value: "home" },
  { label: "Category", value: "category" },
  { label: "Product detail", value: "product_detail" },
  { label: "Pre-sell", value: "pre_sell" },
  { label: "Cart", value: "cart" },
  { label: "Checkout", value: "checkout" },
];

const supportedSiteFamilyHints = [
  { label: "No family hint", value: "" },
  { label: "sales-pdp", value: "sales-pdp" },
  { label: "listicle-presell", value: "listicle-presell" },
  { label: "medusa-b2b-starter", value: "medusa-b2b-starter" },
];

export function SiteImportsPage() {
  const navigate = useNavigate();
  const { importId: routeImportId } = useParams<{ importId?: string }>();
  const { workspace } = useWorkspace();

  // Import creation form state
  const [importUrl, setImportUrl] = useState("");
  const [importArchiveFile, setImportArchiveFile] = useState<File | null>(null);
  const [importPageType, setImportPageType] = useState("");
  const [importSiteFamilyHint, setImportSiteFamilyHint] = useState("");
  const [showAdvancedImport, setShowAdvancedImport] = useState(false);

  // Orchestration state
  const [lastConvertedVariantId, setLastConvertedVariantId] = useState<string | null>(null);
  const [selectedTemplateVariantId, setSelectedTemplateVariantId] = useState<string | null>(null);
  const draftVariantsSectionRef = useRef<HTMLDivElement | null>(null);

  const selectedImportId = routeImportId || null;

  const { data: imports = [], isLoading: importsLoading, refetch: refetchImports } = useSiteImports(
    workspace?.id
  );
  const { data: variants = [], refetch: refetchVariants } = useTemplateVariants(workspace?.id);

  const createImport = useCreateSiteImport();
  const createArchiveImport = useCreateSiteImportFromArchive();

  // Filter variants for selected import
  const variantsForSelectedImport = useMemo(
    () =>
      variants
        .filter((v) => v.siteImportId === selectedImportId)
        .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt)),
    [selectedImportId, variants]
  );

  // Auto-select variant when import changes
  useEffect(() => {
    if (!selectedImportId || !variantsForSelectedImport.length) return;
    const current = variants.find((v) => v.id === selectedTemplateVariantId);
    if (current?.siteImportId === selectedImportId) return;
    setSelectedTemplateVariantId(variantsForSelectedImport[0].id);
  }, [selectedImportId, selectedTemplateVariantId, variants, variantsForSelectedImport]);

  // Reset variant selection and last-converted on import change
  useEffect(() => {
    setLastConvertedVariantId(null);
  }, [selectedImportId]);

  const handleCreateImport = async () => {
    if (!importUrl || !workspace?.id) return;
    try {
      const created = await createImport.mutateAsync({
        sourceUrl: importUrl,
        pageTypeHint: importPageType || undefined,
        siteFamilyHint: importSiteFamilyHint || undefined,
        clientId: workspace.id,
      });
      setImportUrl("");
      setImportPageType("");
      setImportSiteFamilyHint("");
      setShowAdvancedImport(false);
      navigate(`/workspaces/sites/imports/${created.id}`);
      refetchImports();
    } catch (err) {
      console.error("Failed to create import:", err);
    }
  };

  const handleCreateArchiveImport = async () => {
    if (!importArchiveFile || !workspace?.id) return;
    try {
      const created = await createArchiveImport.mutateAsync({
        clientId: workspace.id,
        file: importArchiveFile,
        pageTypeHint: importPageType || undefined,
        siteFamilyHint: importSiteFamilyHint || undefined,
      });
      setImportArchiveFile(null);
      setImportPageType("");
      setImportSiteFamilyHint("");
      setShowAdvancedImport(false);
      navigate(`/workspaces/sites/imports/${created.id}`);
      refetchImports();
    } catch (err) {
      console.error("Failed to create archive import:", err);
    }
  };

  const handleSelectImport = (importId: string) => {
    navigate(`/workspaces/sites/imports/${importId}`);
  };

  const handleDraftConverted = (variantId: string) => {
    setLastConvertedVariantId(variantId);
    setSelectedTemplateVariantId(variantId);
    refetchVariants();
    window.requestAnimationFrame(() => {
      draftVariantsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Site Imports"
          description="Capture, review, and save imported sites."
        />
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to manage site imports."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Site Imports"
        description="Capture reference sites, review the generated output, and save as sites or template drafts."
        actions={
          <Button variant="outline" onClick={() => navigate("/workspaces/sites")}>
            <ArrowLeft className="h-4 w-4" />
            Back to Sites
          </Button>
        }
      >
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-content-muted">
          <Badge tone="accent">Workspace: {workspace.name}</Badge>
        </div>
      </PageHeader>

      {/* Import Form */}
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
          <div>
            <div className="text-sm font-semibold text-content">Import reference site</div>
            <div className="text-xs text-content-muted">
              Capture a live site or upload a React/Tailwind export.
            </div>
          </div>
        </div>

        <div className="mt-4 space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-content">Source URL</label>
            <Input
              type="url"
              placeholder="https://example.com"
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
            />
          </div>

          <div className="rounded-xl border border-dashed border-border px-3 py-3 text-xs text-content-muted">
            <div className="font-semibold text-content">Or upload a screenshot2code React export</div>
            <div className="mt-1">
              Use this when you already have a trusted project zip from outside Marketi.
            </div>
            <div className="mt-3">
              <input
                key={importArchiveFile?.name || "archive-input-empty"}
                type="file"
                accept=".zip,application/zip"
                onChange={(event) => {
                  setImportArchiveFile(event.target.files?.[0] || null);
                }}
                className="block w-full text-sm text-content file:mr-3 file:rounded-lg file:border-0 file:bg-surface-2 file:px-3 file:py-2 file:text-sm file:font-medium"
              />
            </div>
            {importArchiveFile && (
              <div className="mt-2 text-xs text-content">
                Selected: <span className="font-medium">{importArchiveFile.name}</span>
              </div>
            )}
          </div>

          {/* Advanced Options Toggle */}
          <button
            type="button"
            onClick={() => setShowAdvancedImport((prev) => !prev)}
            className="flex items-center gap-1 text-xs text-content-muted hover:text-content"
          >
            {showAdvancedImport ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            Advanced options
          </button>

          {showAdvancedImport && (
            <div className="space-y-3 rounded-xl border border-border bg-surface-2 px-3 py-3">
              <div className="space-y-2">
                <label className="text-xs font-semibold text-content">Page type hint (optional)</label>
                <Select value={importPageType} onValueChange={setImportPageType} options={importPageHintOptions} />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-semibold text-content">Site family hint (optional)</label>
                <Select value={importSiteFamilyHint} onValueChange={setImportSiteFamilyHint} options={supportedSiteFamilyHints} />
              </div>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Button
              onClick={handleCreateImport}
              disabled={!importUrl || createImport.isPending || createArchiveImport.isPending}
              className="w-full"
            >
              {createImport.isPending ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Importing URL...
                </>
              ) : (
                <>
                  <Globe className="mr-2 h-4 w-4" />
                  Import URL
                </>
              )}
            </Button>
            <Button
              variant="secondary"
              onClick={handleCreateArchiveImport}
              disabled={!importArchiveFile || createArchiveImport.isPending || createImport.isPending}
              className="w-full"
            >
              {createArchiveImport.isPending ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Importing Archive...
                </>
              ) : (
                <>
                  <Download className="mr-2 h-4 w-4" />
                  Import Archive
                </>
              )}
            </Button>
          </div>

          {createImport.isError && (
            <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
              {readQueryError(createImport.error, "Failed to create import. Please check the URL and try again.")}
            </div>
          )}
          {createArchiveImport.isError && (
            <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
              {readQueryError(createArchiveImport.error, "Failed to import archive.")}
            </div>
          )}
        </div>
      </div>

      {/* Two-column layout: Sidebar + Detail */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,1fr)]">
        <section ref={draftVariantsSectionRef}>
          <ImportListSidebar
            imports={imports}
            isLoading={importsLoading}
            selectedImportId={selectedImportId}
            onSelectImport={handleSelectImport}
            variants={variants}
            selectedVariantId={selectedTemplateVariantId}
            onSelectVariant={setSelectedTemplateVariantId}
            lastConvertedVariantId={lastConvertedVariantId}
          />

          {/* Variant-level panels (below sidebar when variant selected) */}
          {selectedTemplateVariantId && (
            <div className="mt-4 space-y-4">
              {/* Selected draft info */}
              {(() => {
                const selectedVariant = variants.find((v) => v.id === selectedTemplateVariantId);
                if (!selectedVariant) return null;
                return (
                  <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-content">Selected draft</div>
                        <div className="mt-1 text-xs text-content-muted">
                          Convert creates a template draft, not a saved site page.
                        </div>
                      </div>
                      <Badge tone={selectedVariant.status === "draft" ? "warning" : "success"}>
                        {selectedVariant.status}
                      </Badge>
                    </div>
                    <div className="mt-3 rounded-xl border border-border bg-surface-2 px-3 py-3">
                      <div className="text-sm font-semibold text-content">{selectedVariant.name}</div>
                      <div className="mt-1 text-xs text-content-muted">
                        {selectedVariant.family} / {formatPageType(selectedVariant.pageType)}
                      </div>
                      {selectedVariant.siteImportId === selectedImportId && (
                        <div className="mt-2">
                          <Badge tone="accent">Built from this import</Badge>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

              <VariantMutationPanel
                variantId={selectedTemplateVariantId}
                workspaceId={workspace?.id}
                onVariantGenerated={() => {
                  refetchVariants();
                  setSelectedTemplateVariantId(null);
                }}
              />

              <GovernancePanel
                variantId={selectedTemplateVariantId}
                workspaceId={workspace?.id}
                onApproved={() => refetchVariants()}
              />
            </div>
          )}
        </section>

        <aside>
          {!selectedImportId ? (
            <div className="rounded-2xl border border-border bg-surface px-4 py-8 text-center text-sm text-content-muted">
              Select an import to view details.
            </div>
          ) : (
            <ImportDetailPanel
              importId={selectedImportId}
              workspaceId={workspace.id}
              imports={imports}
              onSiteSaved={() => refetchImports()}
              onDraftConverted={handleDraftConverted}
            />
          )}
        </aside>
      </div>
    </div>
  );
}
