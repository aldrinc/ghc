import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  Globe,
  Layers3,
  Link2,
  Loader2,
  Package2,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";

import {
  useApproveForPublish,
  useConvertImport,
  useCreateDraftFromTemplate,
  useCreateSiteImport,
  useGenerateVariants,
  useMutationPresets,
  useSaveSiteImport,
  useSiteImportDetail,
  useSiteImportSnapshot,
  useSiteImports,
  useStorefrontBindingPreview,
  useStorefrontTemplate,
  useStorefrontTemplates,
  useTemplateVariantDetail,
  useTemplateVariants,
  useVariantGovernance,
  useVariantPresets,
} from "@/api/storefrontTemplates";
import { useProduct, useMedusaConfig, useTestMedusaConnection, useUpdateMedusaConfig, useCreateMedusaVariant } from "@/api/products";
import { useQueryClient } from "@tanstack/react-query";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { cn } from "@/lib/utils";

import type {
  GovernanceReport,
  MutationPresetPreview,
  NormalizedSection,
  ProvenanceEvent,
  SaveSiteImportResponse,
  SiteImportDetail,
  StorefrontBindingPreviewRequirement,
  TemplateVariantDetailExtended,
} from "@/types/storefrontTemplates";
import { useNavigate } from "react-router-dom";
import { ImportActivityPanel } from "@/components/import/ImportActivityPanel";
import type { UpstreamTranscriptEntry, UpstreamVariantData } from "@/types/importActivity";

function readProvenanceString(record: Record<string, unknown> | undefined, ...keys: string[]): string | undefined {
  if (!record) return undefined;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

function readQueryError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function formatPageType(pageType: string): string {
  return pageType
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatSlot(slot: string): string {
  return slot
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatImportModelLabel(modelId?: string, modelSlot?: number): string | undefined {
  if (modelId) return modelId;
  if (modelSlot === 1) return "Slot 1 · Gemini";
  if (modelSlot === 2) return "Slot 2 · Claude Opus";
  return undefined;
}

function resolveFamilyDefaults(family?: string | null): { family: string; pageType: string } {
  if (family === "listicle-presell" || family === "pre-sales-listicle") {
    return { family: "listicle-presell", pageType: "pre_sell" };
  }
  return { family: "sales-pdp", pageType: "product_detail" };
}

function requirementTone(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "ready") return "success";
  if (status === "unsupported") return "danger";
  if (status === "missing") return "warning";
  return "neutral";
}

function isImportActiveStatus(status?: string | null): boolean {
  return Boolean(status && ["queued", "capturing", "generating", "adapting", "running"].includes(status));
}

function RequirementRow({ requirement }: { requirement: StorefrontBindingPreviewRequirement }) {
  const tone = requirementTone(requirement.status);
  const icon =
    tone === "success" ? (
      <CheckCircle2 className="h-4 w-4 text-success" />
    ) : (
      <AlertTriangle className={cn("h-4 w-4", tone === "danger" ? "text-danger" : "text-warning")} />
    );

  return (
    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 shrink-0">{icon}</div>
          <div>
            <div className="text-sm font-semibold text-content">{requirement.label}</div>
            <div className="mt-1 text-xs text-content-muted">{requirement.detail}</div>
          </div>
        </div>
        <Badge tone={tone}>{requirement.status}</Badge>
      </div>
    </div>
  );
}

function MedusaStatusBadge({ status }: { status: string }) {
  if (status === "connected") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
        <CheckCircle2 className="h-3 w-3" />
        Connected
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger">
        <AlertTriangle className="h-3 w-3" />
        Error
      </span>
    );
  }
  if (status === "not_tested") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
        Not tested
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-neutral/10 px-2 py-0.5 text-xs font-medium text-content-muted">
      Not configured
    </span>
  );
}

interface MedusaConnectionCardProps {
  clientId: string;
  productId?: string;
  onVariantCreated?: (variantId: string) => void;
}

function MedusaConnectionCard({ clientId, productId, onVariantCreated }: MedusaConnectionCardProps) {
  const queryClient = useQueryClient();
  const [showConfigForm, setShowConfigForm] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [adminApiKey, setAdminApiKey] = useState("");
  const [showCreateVariant, setShowCreateVariant] = useState(false);
  const [variantTitle, setVariantTitle] = useState("");
  const [variantPrice, setVariantPrice] = useState("");
  const [variantCurrency, setVariantCurrency] = useState("usd");
  const [variantInventoryQuantity, setVariantInventoryQuantity] = useState("");
  const [variantOptionValues, setVariantOptionValues] = useState("");
  const [variantFormError, setVariantFormError] = useState<string | null>(null);

  const { data: config, isLoading: configLoading, refetch: refetchConfig } = useMedusaConfig(clientId);
  const updateConfig = useUpdateMedusaConfig(clientId);
  const testConnection = useTestMedusaConnection(clientId);
  const createVariant = useCreateMedusaVariant(productId || "");

  const handleSaveConfig = async () => {
    if (!baseUrl.trim()) return;
    await updateConfig.mutateAsync({
      baseUrl: baseUrl.trim(),
      adminApiKey: adminApiKey.trim() || undefined,
    });
    setBaseUrl("");
    setAdminApiKey("");
    setShowConfigForm(false);
  };

  const handleTestConnection = async () => {
    await testConnection.mutateAsync();
    refetchConfig();
  };

  const handleCreateVariant = async () => {
    if (!productId || !variantTitle.trim() || !variantPrice || !variantCurrency) return;
    const price = Math.round(parseFloat(variantPrice) * 100);
    if (isNaN(price) || price < 0) return;

    const result = await createVariant.mutateAsync({
      optionValues: variantOptionValues.trim()
        ? JSON.parse(variantOptionValues) as Record<string, string>
        : undefined,
      title: variantTitle.trim(),
      price,
      currency: variantCurrency.toUpperCase(),
      inventoryQuantity: variantInventoryQuantity ? parseInt(variantInventoryQuantity, 10) : undefined,
    });
    setVariantTitle("");
    setVariantPrice("");
    setVariantInventoryQuantity("");
    setVariantOptionValues("");
    setVariantFormError(null);
    setShowCreateVariant(false);
    onVariantCreated?.(result.variantId);
    queryClient.invalidateQueries({ queryKey: ["products", "detail", productId] });
  };

  const handleCreateVariantSafe = async () => {
    try {
      setVariantFormError(null);
      if (variantOptionValues.trim()) {
        const parsed = JSON.parse(variantOptionValues);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          setVariantFormError("Option values must be a JSON object, for example {\"Size\":\"Large\"}.");
          return;
        }
      }
      await handleCreateVariant();
    } catch (error) {
      if (error instanceof SyntaxError) {
        setVariantFormError("Option values must be valid JSON.");
        return;
      }
      throw error;
    }
  };

  const isConnected = config?.connectionStatus === "connected";

  if (configLoading) {
    return (
      <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
        <div className="flex items-center gap-2 text-sm text-content-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading Medusa configuration...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Connection Status Card */}
      <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">Medusa Connection</div>
            <div className="mt-1 text-xs text-content-muted">
              {config?.baseUrl ? (
                <span className="flex items-center gap-1">
                  {config.baseUrl}
                  {config.baseUrl && (
                    <a
                      href={config.baseUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </span>
              ) : (
                "Not configured"
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <MedusaStatusBadge status={config?.connectionStatus || "not_configured"} />
            {config?.baseUrl && (
              <Button size="sm" variant="outline" onClick={handleTestConnection} disabled={testConnection.isPending}>
                {testConnection.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Test"}
              </Button>
            )}
          </div>
        </div>

        {config?.lastConnectionError && (
          <div className="mt-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
            {config.lastConnectionError}
          </div>
        )}

        {!showConfigForm ? (
          <Button
            size="sm"
            variant="outline"
            className="mt-3"
            onClick={() => {
              setBaseUrl(config?.baseUrl || "");
              setShowConfigForm(true);
            }}
          >
            {config?.baseUrl ? "Edit Configuration" : "Configure Medusa"}
          </Button>
        ) : (
          <div className="mt-3 space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Base URL</label>
              <Input
                placeholder="https://my-store.medusa.example.com"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Admin API Key</label>
              <Input
                type="password"
                placeholder="Leave blank to keep existing"
                value={adminApiKey}
                onChange={(e) => setAdminApiKey(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSaveConfig} disabled={updateConfig.isPending || !baseUrl.trim()}>
                {updateConfig.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="mr-1 h-3 w-3" />}
                Save
              </Button>
              <Button size="sm" variant="outline" onClick={() => setShowConfigForm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Create Variant Card - only show if connected and productId provided */}
      {isConnected && productId && (
        <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-content">Create Medusa Variant</div>
              <div className="mt-1 text-xs text-content-muted">
                Create a new variant in Medusa for this product.
              </div>
            </div>
          </div>

          {!showCreateVariant ? (
            <Button size="sm" className="mt-3" onClick={() => setShowCreateVariant(true)}>
              Create Variant
            </Button>
          ) : (
            <div className="mt-3 space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Title *</label>
                <Input
                  placeholder="Variant title"
                  value={variantTitle}
                  onChange={(e) => setVariantTitle(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Price ($) *</label>
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="19.99"
                    value={variantPrice}
                    onChange={(e) => setVariantPrice(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Currency *</label>
                  <Input
                    placeholder="USD"
                    value={variantCurrency}
                    onChange={(e) => setVariantCurrency(e.target.value)}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Inventory</label>
                  <Input
                    type="number"
                    placeholder="Optional"
                    value={variantInventoryQuantity}
                    onChange={(e) => setVariantInventoryQuantity(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Option values (JSON)</label>
                  <Input
                    placeholder='Optional, e.g. {"Format":"Print"}'
                    value={variantOptionValues}
                    onChange={(e) => setVariantOptionValues(e.target.value)}
                  />
                </div>
              </div>
              <div className="text-xs text-content-muted">
                Compare-at pricing is not supported by this Medusa flow yet. Leave it blank and manage it separately if needed.
              </div>
              {variantFormError ? (
                <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
                  {variantFormError}
                </div>
              ) : null}
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleCreateVariantSafe}
                  disabled={createVariant.isPending || !variantTitle.trim() || !variantPrice}
                >
                  {createVariant.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Create"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowCreateVariant(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Helper message when not connected */}
      {!isConnected && productId && (
        <div className="rounded-xl border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <div className="font-medium">Medusa connection required</div>
              <div className="mt-1 text-xs">
                Configure and test your Medusa connection to create variants and use Store Templates.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function StoreTemplatesPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { data: templates = [], isLoading: templatesLoading } = useStorefrontTemplates();
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedProductVariantId, setSelectedProductVariantId] = useState("");
  const [selectedTemplateVariantId, setSelectedTemplateVariantId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"templates" | "imports">("templates");

  // Import state
  const [importUrl, setImportUrl] = useState("");
  const [importPageType, setImportPageType] = useState("");
  const [importSiteFamilyHint, setImportSiteFamilyHint] = useState("");
  const [showAdvancedImport, setShowAdvancedImport] = useState(false);
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
  const [showConvertForm, setShowConvertForm] = useState(false);
  const [convertName, setConvertName] = useState("");
  const [convertFamily, setConvertFamily] = useState("sales-pdp");
  const [convertPageType, setConvertPageType] = useState("product_detail");
  const [selectedSectionIds, setSelectedSectionIds] = useState<string[]>([]);
  const [convertReviewNotes, setConvertReviewNotes] = useState("");
  const [saveSiteName, setSaveSiteName] = useState("");
  const [saveSiteDescription, setSaveSiteDescription] = useState("");
  const [saveResult, setSaveResult] = useState<SaveSiteImportResponse | null>(null);

  // Create draft from template state
  const [showDraftForm, setShowDraftForm] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftReviewNotes, setDraftReviewNotes] = useState("");

  const createDraftFromTemplate = useCreateDraftFromTemplate();

  // Supported families and page types for constrained UI
  const supportedFamilies = [
    { label: "Sales PDP", value: "sales-pdp" },
    { label: "Pre-sales Listicle", value: "listicle-presell" },
  ];
  const supportedPageTypes = [
    { label: "Product Detail", value: "product_detail" },
    { label: "Pre-sell", value: "pre_sell" },
  ];
  const importPageHintOptions = [
    { label: "No page hint", value: "" },
    { label: "Home", value: "home" },
    { label: "Category", value: "category" },
    { label: "Product detail", value: "product_detail" },
    { label: "Cart", value: "cart" },
    { label: "Checkout", value: "checkout" },
  ];
  const supportedSiteFamilyHints = [
    { label: "No family hint", value: "" },
    { label: "medusa-b2b-starter", value: "medusa-b2b-starter" },
  ];

  const { data: imports = [], isLoading: importsLoading, refetch: refetchImports } = useSiteImports(
    workspace?.id
  );
  const { data: importDetail, error: importDetailError, refetch: refetchImportDetail } = useSiteImportDetail(
    selectedImportId || undefined,
    workspace?.id,
    convertFamily || undefined,
    convertPageType || undefined,
    selectedSectionIds.length > 0 ? selectedSectionIds : undefined
  );
  const { data: importSnapshot } = useSiteImportSnapshot(selectedImportId || undefined, workspace?.id);
  const { data: variants = [], refetch: refetchVariants } = useTemplateVariants(workspace?.id);

  const createImport = useCreateSiteImport();
  const convertImport = useConvertImport();
  const saveSiteImport = useSaveSiteImport();

  const activityTranscript = useMemo<UpstreamTranscriptEntry[]>(() => {
    if (!importDetail?.upstreamTranscript) return [];
    return importDetail.upstreamTranscript.map((entry, index) => {
      const typedEntry = entry as Record<string, unknown>;
      const capturedAt = typeof typedEntry.capturedAt === "string" ? typedEntry.capturedAt : undefined;
      return {
        type: String(typedEntry.type || "status") as UpstreamTranscriptEntry["type"],
        value: typeof typedEntry.value === "string" ? typedEntry.value : undefined,
        data: typedEntry.data,
        eventId: typeof typedEntry.eventId === "string" ? typedEntry.eventId : undefined,
        variantIndex: Number(typedEntry.variantIndex ?? 0),
        timestamp: capturedAt ? new Date(capturedAt).getTime() : index,
      };
    });
  }, [importDetail?.upstreamTranscript]);

  const activityVariants = useMemo<UpstreamVariantData[]>(() => {
    if (!importDetail?.upstreamVariants) return [];
    const metadataModels = Array.isArray(importDetail.upstreamMetadata?.variantModels)
      ? (importDetail.upstreamMetadata.variantModels as string[])
      : [];
    return importDetail.upstreamVariants.map((variant, index) => {
      const typedVariant = variant as Record<string, unknown>;
      const variantIndex = Number(typedVariant.variantIndex ?? index);
      const variantEvents = activityTranscript.filter((event) => event.variantIndex === variantIndex);
      const firstEventTimestamp = variantEvents[0]?.timestamp;
      const terminalEvent = [...variantEvents]
        .reverse()
        .find((event) => event.type === "variantComplete" || event.type === "variantError");
      const modelSlot = typeof typedVariant.modelSlot === "number"
        ? typedVariant.modelSlot
        : typeof importDetail.modelSlots?.[variantIndex] === "number"
          ? importDetail.modelSlots[variantIndex]
          : undefined;
      const rawStatus = String(typedVariant.status || "pending");
      const status: UpstreamVariantData["status"] =
        rawStatus === "completed"
          ? "complete"
          : rawStatus === "failed"
            ? "error"
            : rawStatus === "pending"
              ? (isImportActiveStatus(importDetail?.status) ? "generating" : "paused")
              : (rawStatus as UpstreamVariantData["status"]);
      const modelId = typeof typedVariant.modelId === "string"
        ? typedVariant.modelId
        : typeof typedVariant.model === "string"
          ? typedVariant.model
          : typeof metadataModels[variantIndex] === "string"
            ? metadataModels[variantIndex]
            : undefined;
      return {
        variantIndex,
        code: typeof typedVariant.code === "string" ? typedVariant.code : undefined,
        status,
        model: formatImportModelLabel(modelId, modelSlot),
        requestStartedAt: firstEventTimestamp,
        completedAt: terminalEvent?.timestamp,
      };
    });
  }, [activityTranscript, importDetail?.status, importDetail?.upstreamMetadata, importDetail?.upstreamVariants]);

  useEffect(() => {
    if (!templates.length) return;
    if (!selectedTemplateId || !templates.some((template) => template.id === selectedTemplateId)) {
      setSelectedTemplateId(templates[0]?.id || "");
    }
  }, [selectedTemplateId, templates]);

  useEffect(() => {
    setSelectedProductVariantId("");
  }, [product?.id]);

  // Clear section selection when selected import changes
  useEffect(() => {
    setSelectedSectionIds([]);
    setSaveResult(null);
  }, [selectedImportId]);

  useEffect(() => {
    if (!selectedImportId) return;
    const selectedImport = imports.find((item) => item.id === selectedImportId);
    if (!selectedImport) return;
    const defaults = resolveFamilyDefaults(selectedImport.suggestedTemplateFamily);
    setConvertFamily(defaults.family);
    setConvertPageType(defaults.pageType);
    setSaveSiteName(selectedImport.title || selectedImport.sourceHostname || "Imported Site");
    setSaveSiteDescription("");
  }, [selectedImportId, imports]);

  useEffect(() => {
    if (!selectedImportId || !isImportActiveStatus(importDetail?.status)) return;
    const intervalId = window.setInterval(() => {
      void refetchImports();
      void refetchImportDetail();
    }, 1500);
    return () => window.clearInterval(intervalId);
  }, [importDetail?.status, refetchImportDetail, refetchImports, selectedImportId]);

  const { data: templateDetail, error: templateDetailError } = useStorefrontTemplate(
    selectedTemplateId || undefined
  );
  const { data: productDetail, refetch: refetchProductDetail } = useProduct(product?.id);
  const { data: medusaConfig } = useMedusaConfig(workspace?.id);
  const variantOptions = useMemo(
    () => [
      { label: "No variant selected", value: "" },
      ...(productDetail?.variants || []).map((variant) => ({
        label: `${variant.title} - ${(variant.provider || "no provider").toUpperCase()}`,
        value: variant.id,
      })),
    ],
    [productDetail?.variants]
  );

  const bindingPreview = useStorefrontBindingPreview({
    templateId: selectedTemplateId || undefined,
    clientId: workspace?.id,
    productId: product?.id,
    variantId: selectedProductVariantId || undefined,
  });

  const selectedRuntimeVariant = useMemo(
    () => productDetail?.variants?.find((variant) => variant.id === selectedProductVariantId),
    [productDetail?.variants, selectedProductVariantId]
  );

  const medusaWorkspaceReady = medusaConfig?.connectionStatus === "connected";
  const effectiveBindingReady = Boolean(
    bindingPreview.data?.ready &&
      (!selectedRuntimeVariant ||
        (selectedRuntimeVariant.provider || "").toLowerCase() !== "medusa" ||
        medusaWorkspaceReady)
  );

  const handleCreateImport = async () => {
    if (!importUrl || !workspace?.id) return;
    try {
      const createdImport = await createImport.mutateAsync({
        sourceUrl: importUrl,
        pageTypeHint: importPageType || undefined,
        siteFamilyHint: importSiteFamilyHint || undefined,
        clientId: workspace.id,
      });
      setImportUrl("");
      setImportPageType("");
      setImportSiteFamilyHint("");
      setShowAdvancedImport(false);
      setSelectedImportId(createdImport.id);
      setActiveTab("imports");
      refetchImports();
    } catch (err) {
      console.error("Failed to create import:", err);
    }
  };

  const handleConvertImport = async () => {
    if (!selectedImportId || !workspace?.id || !convertName) return;
    try {
      await convertImport.mutateAsync({
        importId: selectedImportId,
        clientId: workspace.id,
        name: convertName,
        family: convertFamily,
        pageType: convertPageType,
        acceptedSectionIds: selectedSectionIds,
        reviewNotes: convertReviewNotes || undefined,
      });
      setShowConvertForm(false);
      setConvertName("");
      setSelectedSectionIds([]);
      setConvertReviewNotes("");
      // Refresh draft variants and import detail after successful conversion
      refetchVariants();
      refetchImportDetail();
    } catch (err) {
      console.error("Failed to convert import:", err);
    }
  };

  const handleSaveSiteImport = async () => {
    if (!selectedImportId || !workspace?.id || !saveSiteName.trim()) return;
    try {
      const result = await saveSiteImport.mutateAsync({
        importId: selectedImportId,
        clientId: workspace.id,
        siteName: saveSiteName.trim(),
        description: saveSiteDescription.trim() || undefined,
      });
      setSaveResult(result);
      refetchImportDetail();
    } catch (err) {
      console.error("Failed to save site import:", err);
    }
  };

  const handleCreateDraftFromTemplate = async () => {
    if (!selectedTemplateId || !product?.id || !selectedProductVariantId || !draftName || !workspace?.id) return;
    try {
      await createDraftFromTemplate.mutateAsync({
        templateId: selectedTemplateId,
        clientId: workspace.id,
        name: draftName,
        productId: product.id,
        variantId: selectedProductVariantId,
        reviewNotes: draftReviewNotes || undefined,
      });
      setShowDraftForm(false);
      setDraftName("");
      setDraftReviewNotes("");
      refetchVariants();
    } catch (err) {
      console.error("Failed to create draft from template:", err);
    }
  };

  const toggleSection = (sectionId: string) => {
    setSelectedSectionIds((prev) =>
      prev.includes(sectionId) ? prev.filter((id) => id !== sectionId) : [...prev, sectionId]
    );
  };

  const statusTone = (status: string): "success" | "warning" | "danger" | "neutral" => {
    if (status === "completed") return "success";
    if (["queued", "capturing", "generating", "adapting", "running"].includes(status)) return "warning";
    if (status === "failed") return "danger";
    return "neutral";
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Store templates" description="Select a workspace to browse template families." />
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to browse storefront templates and Medusa binding readiness."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Store templates"
        description="Browse the first storefront-ready template families derived from the existing funnel system."
      >
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-content-muted">
          <Badge tone="accent">Workspace: {workspace.name}</Badge>
          {product ? <Badge tone="neutral">Product: {product.title}</Badge> : <Badge tone="warning">No product selected</Badge>}
        </div>
      </PageHeader>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-border">
        <button
          type="button"
          onClick={() => setActiveTab("templates")}
          className={cn(
            "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "templates"
              ? "border-accent text-accent"
              : "border-transparent text-content-muted hover:text-content"
          )}
        >
          <Layers3 className="mr-2 inline h-4 w-4" />
          Template Families
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("imports")}
          className={cn(
            "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "imports"
              ? "border-accent text-accent"
              : "border-transparent text-content-muted hover:text-content"
          )}
        >
          <Download className="mr-2 inline h-4 w-4" />
          Import Reference Site
          {imports.length > 0 && (
            <Badge tone="neutral" className="ml-2">
              {imports.length}
            </Badge>
          )}
        </button>
      </div>

      {activeTab === "templates" ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <section className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Template families</div>
                <div className="text-xs text-content-muted">
                  Start with the current funnel templates, then layer in Medusa bindings and design-system control.
                </div>
              </div>
              <Badge tone="neutral">{templates.length} templates</Badge>
            </div>

            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {templatesLoading ? (
                <div className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted lg:col-span-2">
                  Loading storefront templates...
                </div>
              ) : null}

              {!templatesLoading && !templates.length ? (
                <div className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted lg:col-span-2">
                  No storefront templates are registered yet.
                </div>
              ) : null}

              {templates.map((template) => {
                const active = template.id === selectedTemplateId;
                return (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => setSelectedTemplateId(template.id)}
                    className={cn(
                      "rounded-2xl border px-4 py-4 text-left transition-colors",
                      active
                        ? "border-accent bg-accent/5 shadow-sm"
                        : "border-border bg-surface-2 hover:border-accent/40 hover:bg-surface"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">
                          {template.family}
                        </div>
                        <div className="mt-1 text-base font-semibold text-content">{template.name}</div>
                      </div>
                      <Badge tone="neutral">{formatPageType(template.pageType)}</Badge>
                    </div>
                    <div className="mt-2 text-sm text-content-muted">{template.description || "No description"}</div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {template.requiredBindingKeys.map((bindingKey) => (
                        <Badge key={bindingKey} tone="accent" className="font-medium">
                          {bindingKey}
                        </Badge>
                      ))}
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-content-muted">
                      <div>
                        <div className="font-semibold text-content">Variant</div>
                        <div>{template.variant}</div>
                      </div>
                      <div>
                        <div className="font-semibold text-content">Version</div>
                        <div>{template.version}</div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-start justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Template detail</div>
                <div className="text-xs text-content-muted">Family metadata, slot controls, and token policy.</div>
              </div>
              {templateDetail ? <Badge tone="neutral">{templateDetail.id}</Badge> : null}
            </div>

            {templateDetailError ? (
              <div className="mt-4 rounded-xl border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
                {readQueryError(templateDetailError, "Failed to load template detail.")}
              </div>
            ) : null}

            {!templateDetail ? (
              <div className="py-6 text-sm text-content-muted">Select a template to inspect its storefront metadata.</div>
            ) : (
              <div className="space-y-4 pt-4">
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                  <div className="flex items-start gap-3">
                    <Layers3 className="mt-0.5 h-4 w-4 text-accent" />
                    <div>
                      <div className="text-sm font-semibold text-content">{templateDetail.family}</div>
                      <div className="mt-1 text-xs text-content-muted">
                        {formatPageType(templateDetail.pageType)} variant `{templateDetail.variant}`
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
                  <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-content">
                      <Package2 className="h-4 w-4 text-accent" />
                      Configuration slots
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {templateDetail.configSlots.map((slot) => (
                        <Badge key={slot} tone="neutral">
                          {formatSlot(slot)}
                        </Badge>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-content">
                      <Link2 className="h-4 w-4 text-accent" />
                      Token policy
                    </div>
                    <div className="mt-3 space-y-3 text-xs text-content-muted">
                      <div>
                        <div className="font-semibold uppercase tracking-wide text-content">Locked</div>
                        <div className="mt-1 flex flex-wrap gap-2">
                          {templateDetail.stylePolicy.lockedTokenGroups.map((group) => (
                            <Badge key={group} tone="warning">
                              {group}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <div>
                        <div className="font-semibold uppercase tracking-wide text-content">Editable</div>
                        <div className="mt-1 flex flex-wrap gap-2">
                          {templateDetail.stylePolicy.editableTokenGroups.map((group) => (
                            <Badge key={group} tone="success">
                              {group}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                  <div className="text-sm font-semibold text-content">Binding contract</div>
                  <div className="mt-3 space-y-3">
                    {templateDetail.requiredBindings.map((binding) => (
                      <div key={binding.key} className="rounded-xl border border-border bg-surface px-3 py-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-sm font-semibold text-content">{binding.label}</div>
                          <Badge tone={binding.source === "medusa" ? "accent" : "neutral"}>{binding.source}</Badge>
                        </div>
                        <div className="mt-1 text-xs text-content-muted">{binding.description}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                  <div className="text-sm font-semibold text-content">Import provenance</div>
                  <div className="mt-2 text-xs text-content-muted">
                    Source: {templateDetail.importProvenance.sourceType} / {templateDetail.importProvenance.sourceTemplateId}
                  </div>
                  <div className="mt-3 space-y-2 text-xs text-content-muted">
                    {templateDetail.importProvenance.notes.map((note) => (
                      <div key={note}>{note}</div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-start justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Binding readiness</div>
                <div className="text-xs text-content-muted">
                  Evaluate the selected workspace product and variant against the template contract.
                </div>
              </div>
              {bindingPreview.data ? (
                <Badge tone={effectiveBindingReady ? "success" : "warning"}>
                  {effectiveBindingReady ? "Ready" : "Needs work"}
                </Badge>
              ) : null}
            </div>

            <div className="space-y-4 pt-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Variant</label>
                <Select value={selectedProductVariantId} onValueChange={setSelectedProductVariantId} options={variantOptions} />
                <div className="text-xs text-content-muted">
                  {product ? "No implicit variant selection is applied." : "Select a product in the header to evaluate runtime bindings."}
                </div>
              </div>

              {/* Medusa Connection Card */}
              {workspace?.id && (
                <MedusaConnectionCard
                  clientId={workspace.id}
                  productId={product?.id}
                  onVariantCreated={async (variantId) => {
                    await refetchProductDetail();
                    setSelectedProductVariantId(variantId);
                  }}
                />
              )}

              {bindingPreview.isLoading ? <div className="text-sm text-content-muted">Evaluating bindings...</div> : null}

              {bindingPreview.error ? (
                <div className="rounded-xl border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
                  {readQueryError(bindingPreview.error, "Failed to evaluate binding readiness.")}
                </div>
              ) : null}

              {bindingPreview.data ? (
                <>
                  <div className="rounded-xl border border-border bg-surface-2 px-4 py-4 text-xs text-content-muted">
                    <div className="font-semibold text-content">Current context</div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <div>
                        <div className="font-semibold text-content">Product</div>
                        <div>{bindingPreview.data.productTitle || "Not selected"}</div>
                      </div>
                      <div>
                        <div className="font-semibold text-content">Variant provider</div>
                        <div>{bindingPreview.data.variantProvider || "Not selected"}</div>
                      </div>
                    </div>
                    {selectedRuntimeVariant &&
                    (selectedRuntimeVariant.provider || "").toLowerCase() === "medusa" &&
                    !medusaWorkspaceReady ? (
                      <div className="mt-3 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
                        This variant is marked as Medusa-managed, but the workspace Medusa connection is not currently healthy.
                      </div>
                    ) : null}
                  </div>

                  <div className="space-y-3">
                    {bindingPreview.data.requirements.map((requirement) => (
                      <RequirementRow key={requirement.key} requirement={requirement} />
                    ))}
                  </div>

                  <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                    <div className="text-xs font-semibold uppercase tracking-wide text-content">Notes</div>
                    <div className="mt-2 space-y-2 text-xs text-content-muted">
                      {bindingPreview.data.notes.map((note) => (
                        <div key={note}>{note}</div>
                      ))}
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>

          {/* Create Draft from Template */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-start justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Create draft from template</div>
                <div className="text-xs text-content-muted">
                  Create a variant draft directly from the selected built-in template.
                </div>
              </div>
              {effectiveBindingReady ? (
                <Badge tone="success">Ready</Badge>
              ) : (
                <Badge tone="warning">Needs setup</Badge>
              )}
            </div>

            <div className="space-y-4 pt-4">
              {!showDraftForm ? (
                <>
                  <div className="rounded-xl border border-dashed border-border px-4 py-4 text-sm text-content-muted">
                    <div className="flex items-start gap-3">
                      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                      <div>
                        <div className="font-medium text-content">Skip site import</div>
                        <div className="mt-1">
                          Create a draft variant directly from a built-in storefront template. Requires a Medusa-ready
                          product variant.
                        </div>
                      </div>
                    </div>
                  </div>
                  <Button
                    onClick={() => setShowDraftForm(true)}
                    disabled={!effectiveBindingReady || !product || !selectedProductVariantId}
                    className="w-full"
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    Create Draft from Template
                  </Button>
                  {!product && (
                    <div className="text-xs text-content-muted">
                      Select a product in the header to enable draft creation.
                    </div>
                  )}
                  {product && !selectedProductVariantId && (
                    <div className="text-xs text-content-muted">
                      Select a variant above to enable draft creation.
                    </div>
                  )}
                  {product && selectedProductVariantId && !effectiveBindingReady && (
                    <div className="text-xs text-warning">
                      Binding requirements and workspace Medusa health must both be ready to create a draft.
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-content">Draft name</label>
                      <Input
                        placeholder="My variant draft"
                        value={draftName}
                        onChange={(e) => setDraftName(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-content">Review notes (optional)</label>
                      <Input
                        placeholder="Notes for reviewers"
                        value={draftReviewNotes}
                        onChange={(e) => setDraftReviewNotes(e.target.value)}
                      />
                    </div>
                    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                      <div className="font-semibold text-content">Template</div>
                      <div className="mt-1">
                        {templateDetail?.name || selectedTemplateId}
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        <div>
                          <div className="font-medium text-content">Family</div>
                          <div>{templateDetail?.family || "-"}</div>
                        </div>
                        <div>
                          <div className="font-medium text-content">Page type</div>
                          <div>{templateDetail?.pageType ? formatPageType(templateDetail.pageType) : "-"}</div>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        onClick={handleCreateDraftFromTemplate}
                        disabled={!draftName || createDraftFromTemplate.isPending}
                        className="flex-1"
                      >
                        {createDraftFromTemplate.isPending ? (
                          <>
                            <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                            Creating...
                          </>
                        ) : (
                          <>
                            <Sparkles className="mr-2 h-4 w-4" />
                            Create Draft
                          </>
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          setShowDraftForm(false);
                          setDraftName("");
                          setDraftReviewNotes("");
                        }}
                        disabled={createDraftFromTemplate.isPending}
                      >
                        Cancel
                      </Button>
                    </div>
                    {createDraftFromTemplate.isError && (
                      <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
                        {readQueryError(createDraftFromTemplate.error, "Failed to create draft. Please try again.")}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Draft Variants from Templates */}
          {variants.filter((v) => v.sourceType === "storefront_template").length > 0 && (
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
                <div>
                  <div className="text-sm font-semibold text-content">Template drafts</div>
                  <div className="text-xs text-content-muted">
                    Variants created from built-in templates.
                  </div>
                </div>
                <Badge tone="neutral">
                  {variants.filter((v) => v.sourceType === "storefront_template").length}
                </Badge>
              </div>
              <div className="mt-4 space-y-2">
                {variants
                  .filter((v) => v.sourceType === "storefront_template")
                  .map((variant) => (
                    <button
                      key={variant.id}
                      type="button"
                      onClick={() => setSelectedTemplateVariantId(variant.id)}
                      className={cn(
                        "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                        selectedTemplateVariantId === variant.id
                          ? "border-accent bg-accent/5"
                          : "border-border bg-surface-2 hover:border-accent/40"
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-semibold text-content">{variant.name}</div>
                          <div className="mt-1 text-xs text-content-muted">
                            {variant.family} / {formatPageType(variant.pageType)}
                          </div>
                        </div>
                        <Badge tone={variant.status === "draft" ? "warning" : "success"}>
                          {variant.status}
                        </Badge>
                      </div>
                    </button>
                  ))}
              </div>
            </div>
          )}

          {/* Template Draft Governance Panel */}
          {selectedTemplateVariantId && (() => {
            const selectedVariant = variants.find((v) => v.id === selectedTemplateVariantId);
            return selectedVariant?.sourceType === "storefront_template";
          })() && (
            <GovernancePanel
              variantId={selectedTemplateVariantId}
              workspaceId={workspace?.id}
              onApproved={() => {
                refetchVariants();
              }}
            />
          )}
        </aside>
      </div>
      ) : (
        /* Imports Tab */
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,1fr)]">
          <section className="space-y-4">
            {/* Import Form */}
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
                <div>
                  <div className="text-sm font-semibold text-content">Import reference site</div>
                  <div className="text-xs text-content-muted">
                    Capture a live site to create a template variant draft.
                  </div>
                </div>
              </div>

              <div className="mt-4 space-y-4">
                <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                  <div className="font-semibold text-content">Default import settings</div>
                  <div className="mt-2 grid gap-2 sm:grid-cols-3">
                    <div>
                      <div className="font-medium text-content">Stack</div>
                      <div>react_tailwind</div>
                    </div>
                    <div>
                      <div className="font-medium text-content">Model slots</div>
                      <div>1 = Gemini, 2 = Claude Opus</div>
                    </div>
                    <div>
                      <div className="font-medium text-content">Import engine</div>
                      <div>screenshot-to-code</div>
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-content">Source URL</label>
                  <Input
                    type="url"
                    placeholder="https://example.com"
                    value={importUrl}
                    onChange={(e) => setImportUrl(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-content">Page type hint (optional)</label>
                  <Select value={importPageType} onValueChange={setImportPageType} options={importPageHintOptions} />
                  <div className="text-xs text-content-muted">
                    Use supported Marketi page roles only. This prevents adapter mismatches with unsupported shorthand values.
                  </div>
                </div>

                {/* Advanced Options Toggle */}
                <div className="pt-2">
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
                </div>

                {/* Advanced Options Panel */}
                {showAdvancedImport && (
                  <div className="space-y-3 rounded-xl border border-border bg-surface-2 px-3 py-3">
                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-content">Site family hint (optional)</label>
                      <Select
                        value={importSiteFamilyHint}
                        onValueChange={setImportSiteFamilyHint}
                        options={supportedSiteFamilyHints}
                      />
                      <div className="text-xs text-content-muted">
                        Use a real site family id when the adapter cannot infer the family from screenshot-to-code output.
                        Current supported runtime family: <span className="font-semibold text-content">medusa-b2b-starter</span>.
                      </div>
                    </div>
                  </div>
                )}

                <Button
                  onClick={handleCreateImport}
                  disabled={!importUrl || createImport.isPending}
                  className="w-full"
                >
                  {createImport.isPending ? (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      Importing...
                    </>
                  ) : (
                    <>
                      <Download className="mr-2 h-4 w-4" />
                      Start Import
                    </>
                  )}
                </Button>

                {createImport.isError && (
                  <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
                    {readQueryError(createImport.error, "Failed to create import. Please check the URL and try again.")}
                  </div>
                )}
              </div>
            </div>

            {/* Import History */}
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
                <div>
                  <div className="text-sm font-semibold text-content">Import history</div>
                  <div className="text-xs text-content-muted">
                    Previously imported reference sites.
                  </div>
                </div>
                <Badge tone="neutral">{imports.length} imports</Badge>
              </div>

              <div className="mt-4 space-y-2">
                {importsLoading ? (
                  <div className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted">
                    Loading imports...
                  </div>
                ) : !imports.length ? (
                  <div className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted">
                    No imports yet. Use the form above to import a reference site.
                  </div>
                ) : (
                  imports.map((imp) => {
                    const selected = imp.id === selectedImportId;
                    return (
                      <button
                        key={imp.id}
                        type="button"
                        onClick={() => setSelectedImportId(imp.id)}
                        className={cn(
                          "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                          selected
                            ? "border-accent bg-accent/5"
                            : "border-border bg-surface-2 hover:border-accent/40"
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-semibold text-content">
                              {imp.title || imp.sourceHostname || imp.sourceUrl}
                            </div>
                            <div className="mt-1 truncate text-xs text-content-muted">{imp.sourceUrl}</div>
                          </div>
                          <Badge tone={statusTone(imp.status)}>{imp.status}</Badge>
                        </div>
                        <div className="mt-2 flex items-center gap-3 text-xs text-content-muted">
                          <span>{imp.suggestedTemplateFamily || "No suggestion"}</span>
                          <span>
                            {new Date(imp.createdAt).toLocaleDateString()}
                          </span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Draft Variants */}
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
                <div>
                  <div className="text-sm font-semibold text-content">Draft variants</div>
                  <div className="text-xs text-content-muted">
                    Template variants created from imports.
                  </div>
                </div>
                <Badge tone="neutral">{variants.length} variants</Badge>
              </div>

              <div className="mt-4 space-y-2">
                {!variants.length ? (
                  <div className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted">
                    No draft variants yet. Convert an import to create one.
                  </div>
                ) : (
                  variants.map((variant) => (
                    <button
                      key={variant.id}
                      type="button"
                          onClick={() => setSelectedTemplateVariantId(variant.id)}
                          className={cn(
                            "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                            selectedTemplateVariantId === variant.id
                              ? "border-accent bg-accent/5"
                              : "border-border bg-surface-2 hover:border-accent/40"
                          )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-semibold text-content">{variant.name}</div>
                          <div className="mt-1 text-xs text-content-muted">
                            {variant.family} / {formatPageType(variant.pageType)}
                          </div>
                          {variant.mutationPresetLabel ? (
                            <div className="mt-2">
                              <Badge tone="accent">{variant.mutationPresetLabel}</Badge>
                            </div>
                          ) : null}
                        </div>
                        <Badge tone={variant.status === "draft" ? "warning" : "success"}>
                          {variant.status}
                        </Badge>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* Variant Mutation Panel */}
            {selectedTemplateVariantId && (
              <VariantMutationPanel
                variantId={selectedTemplateVariantId}
                workspaceId={workspace?.id}
                onVariantGenerated={() => {
                  refetchVariants();
                  setSelectedTemplateVariantId(null);
                }}
              />
            )}

            {/* Governance Panel */}
            {selectedTemplateVariantId && (
              <GovernancePanel
                variantId={selectedTemplateVariantId}
                workspaceId={workspace?.id}
                onApproved={() => {
                  refetchVariants();
                }}
              />
            )}
          </section>

          {/* Import Detail Panel */}
          <aside className="space-y-4">
            {!selectedImportId ? (
              <div className="rounded-2xl border border-border bg-surface px-4 py-8 text-center text-sm text-content-muted">
                Select an import to view details.
              </div>
            ) : importDetailError ? (
              <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-8 text-center text-sm text-danger">
                {readQueryError(importDetailError, "Failed to load import details.")}
              </div>
            ) : importDetail ? (
              <>
                {/* Screenshots */}
                {importSnapshot && (
                  <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                    <div className="text-sm font-semibold text-content">Screenshots</div>
                    <div className="mt-3 space-y-3">
                      <div>
                        <div className="text-xs font-semibold text-content-muted">Desktop</div>
                        <div className="mt-1 overflow-hidden rounded-lg border border-border">
                          <img
                            src={importSnapshot.desktopScreenshotDataUrl}
                            alt="Desktop snapshot"
                            className="w-full"
                          />
                        </div>
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-content-muted">Mobile</div>
                        <div className="mt-1 overflow-hidden rounded-lg border border-border">
                          <img
                            src={importSnapshot.mobileScreenshotDataUrl}
                            alt="Mobile snapshot"
                            className="w-full max-w-[200px]"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-content">Import progress</div>
                      <div className="text-xs text-content-muted">
                        Exact pipeline stage and backend-reported status for this run.
                      </div>
                    </div>
                    <Badge tone={statusTone(importDetail.status)}>{importDetail.status}</Badge>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                      <div className="font-semibold text-content">Input mode</div>
                      <div className="mt-1">{importDetail.inputMode || "image"}</div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                      <div className="font-semibold text-content">Model slots</div>
                      <div className="mt-1">
                        {importDetail.modelSlots.length ? importDetail.modelSlots.join(", ") : "Default slot set"}
                      </div>
                    </div>
                  </div>
                  {(importDetail.captureError || importDetail.generatorError) && (
                    <div className="mt-3 rounded-xl border border-danger/30 bg-danger/5 px-3 py-3 text-sm text-danger">
                      <div className="font-semibold">{importDetail.failureStage || "Import failed"}</div>
                      <div className="mt-1">{importDetail.generatorError || importDetail.captureError}</div>
                    </div>
                  )}
                </div>

                <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-content">Site-level review</div>
                      <div className="text-xs text-content-muted">
                        Adapter-backed family, entry page, completeness, and imported page set.
                      </div>
                    </div>
                    {importDetail.savedSiteId ? <Badge tone="success">Saved</Badge> : null}
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                      <div className="font-semibold text-content">Resolved family</div>
                      <div className="mt-1">
                        {importDetail.resolvedSiteFamily || importDetail.suggestedTemplateFamily || "Unresolved"}
                      </div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                      <div className="font-semibold text-content">Family hint</div>
                      <div className="mt-1">{importDetail.siteFamilyHint || "None"}</div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                      <div className="font-semibold text-content">Entry page</div>
                      <div className="mt-1">
                        {String(importDetail.adaptedSite?.entry_page_type || importDetail.adaptedSite?.entryPageType || importDetail.resolvedPageType || "Unknown")}
                      </div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                      <div className="font-semibold text-content">Completeness</div>
                      <div className="mt-1">
                        {String(importDetail.adaptedSite?.completeness_state || importDetail.adaptedSite?.completenessState || "partial")}
                      </div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                      <div className="font-semibold text-content">Imported pages</div>
                      <div className="mt-1">{importDetail.adaptedPages.length || 0}</div>
                    </div>
                  </div>
                  {importDetail.adaptedPages.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      {importDetail.adaptedPages.map((page, index) => {
                        const pageType = String(page.page_type || page.pageType || `page_${index + 1}`);
                        const templateId = String(page.template_id || page.templateId || "unmapped");
                        const outboundLinks = Array.isArray(page.outbound_links || page.outboundLinks)
                          ? (page.outbound_links || page.outboundLinks)
                          : [];
                        return (
                          <div key={`${pageType}-${index}`} className="rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="font-semibold text-content">{formatPageType(pageType)}</div>
                                <div className="mt-1">Template: {templateId}</div>
                              </div>
                              <Badge tone="neutral">#{index + 1}</Badge>
                            </div>
                            <div className="mt-2 grid gap-2 sm:grid-cols-2">
                              <div>
                                <span className="font-semibold text-content">Slug:</span> {String(page.slug || "-")}
                              </div>
                              <div>
                                <span className="font-semibold text-content">Links:</span> {outboundLinks.length}
                              </div>
                              <div>
                                <span className="font-semibold text-content">Generated code:</span>{" "}
                                {page.generated_code || page.generatedCode ? "Available" : "Unavailable"}
                              </div>
                              <div>
                                <span className="font-semibold text-content">Puck data:</span>{" "}
                                {Object.keys((page.puck_data || page.puckData || {}) as Record<string, unknown>).length
                                  ? "Available"
                                  : "Unavailable"}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-dashed border-border px-3 py-4 text-sm text-content-muted">
                      No adapter-backed page set is available yet.
                    </div>
                  )}
                </div>

                {/* Generator Activity Panel */}
                <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-content">Generator activity</div>
                      <div className="text-xs text-content-muted">
                        Detailed screenshot-to-code progress and events.
                      </div>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-content-muted">
                      <span>{importDetail.upstreamTranscript.length} events</span>
                      <span>•</span>
                      <span>{importDetail.upstreamVariants.length} variants</span>
                    </div>
                  </div>
                  <div className="mt-3">
                    <ImportActivityPanel
                      transcript={activityTranscript}
                      variants={activityVariants}
                      isActive={isImportActiveStatus(importDetail.status)}
                    />
                  </div>
                  {/* Metadata summary */}
                  <div className="mt-4 rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                    <div className="font-semibold text-content">Generator metadata</div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <div>Generator: {String(importDetail.upstreamMetadata.generatorSystem || "screenshot-to-code")}</div>
                      <div>Stack: {String(importDetail.upstreamMetadata.stack || "react_tailwind")}</div>
                      <div>Variant count: {String(importDetail.upstreamMetadata.variantCount || importDetail.upstreamVariants.length)}</div>
                      <div>Models: {Array.isArray(importDetail.upstreamMetadata.variantModels) ? importDetail.upstreamMetadata.variantModels.join(", ") : "-"}</div>
                    </div>
                  </div>
                </div>

                {/* Theme Candidate */}
                {importDetail.themeCandidate && Object.keys(importDetail.themeCandidate).length > 0 && (
                  <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-content">
                      <Sparkles className="h-4 w-4 text-accent" />
                      Theme candidate
                    </div>
                    <div className="mt-3 space-y-3">
                      {importDetail.themeCandidate.palette && (
                        <div>
                          <div className="text-xs font-semibold text-content-muted">Palette</div>
                          <div className="mt-1 flex flex-wrap gap-2">
                            {Object.entries(importDetail.themeCandidate.palette)
                              .filter(([, v]) => v)
                              .map(([key, value]) => (
                                <div key={key} className="flex items-center gap-2 rounded-lg border border-border px-2 py-1">
                                  <div
                                    className="h-3 w-3 rounded-full border border-border"
                                    style={{ backgroundColor: value || undefined }}
                                  />
                                  <span className="text-xs text-content-muted">{key}</span>
                                </div>
                              ))}
                          </div>
                        </div>
                      )}
                      {importDetail.themeCandidate.fonts && (
                        <div>
                          <div className="text-xs font-semibold text-content-muted">Fonts</div>
                          <div className="mt-1 flex flex-wrap gap-2">
                            {Object.entries(importDetail.themeCandidate.fonts)
                              .filter(([, v]) => v)
                              .map(([key, value]) => (
                                <Badge key={key} tone="neutral">
                                  {key}: {value}
                                </Badge>
                              ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Normalized Sections */}
                {importDetail.normalizedSections && importDetail.normalizedSections.length > 0 && (
                  <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                    <div className="text-sm font-semibold text-content">Normalized sections</div>
                    <div className="mt-3 space-y-2">
                      {importDetail.normalizedSections.map((section) => (
                        <button
                          key={section.id}
                          type="button"
                          onClick={() => toggleSection(section.id)}
                          className={cn(
                            "w-full rounded-xl border px-3 py-2 text-left transition-colors",
                            selectedSectionIds.includes(section.id)
                              ? "border-accent bg-accent/5"
                              : "border-border bg-surface-2"
                          )}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div>
                              <div className="text-sm font-semibold text-content">{section.sectionType}</div>
                              <div className="text-xs text-content-muted">
                                Confidence: {(section.confidence * 100).toFixed(0)}%
                              </div>
                            </div>
                            {selectedSectionIds.includes(section.id) ? (
                              <CheckCircle2 className="h-4 w-4 text-accent" />
                            ) : (
                              <div className="h-4 w-4 rounded-full border border-border" />
                            )}
                          </div>
                          {section.keyText && section.keyText.length > 0 && (
                            <div className="mt-2 text-xs text-content-muted">
                              {section.keyText.slice(0, 2).join(", ")}
                              {section.keyText.length > 2 && ` +${section.keyText.length - 2} more`}
                            </div>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Synthesis Output */}
                {importDetail.synthesis && (
                  <>
                    {/* Block Coverage Summary */}
                    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                      <div className="flex items-center gap-2 text-sm font-semibold text-content">
                        <Layers3 className="h-4 w-4 text-accent" />
                        Block coverage
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-3">
                        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
                          <div className="text-xs text-content-muted">Coverage Score</div>
                          <div className="mt-1 text-xl font-bold text-content">
                            {(importDetail.synthesis.blockCoverage.coverageScore * 100).toFixed(0)}%
                          </div>
                        </div>
                        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
                          <div className="text-xs text-content-muted">Exact Matches</div>
                          <div className="mt-1 text-xl font-bold text-success">
                            {importDetail.synthesis.blockCoverage.exactMatches}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
                          <div className="text-xs text-content-muted">Partial Matches</div>
                          <div className="mt-1 text-xl font-bold text-warning">
                            {importDetail.synthesis.blockCoverage.partialMatches}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
                          <div className="text-xs text-content-muted">Missing</div>
                          <div className="mt-1 text-xl font-bold text-danger">
                            {importDetail.synthesis.blockCoverage.missingMatches}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Block Mapping Details */}
                    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                      <div className="text-sm font-semibold text-content">Mapped blocks</div>
                      <div className="mt-3 space-y-2">
                        {importDetail.synthesis.blockCoverageDetails.map((detail) => (
                          <div
                            key={detail.sectionId}
                            className="rounded-xl border border-border bg-surface-2 px-3 py-2"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <div>
                                <div className="text-sm font-semibold text-content">{detail.sectionType}</div>
                                <div className="text-xs text-content-muted">
                                  {detail.mappedBlock ? `Mapped to: ${detail.mappedBlock}` : "No mapping"}
                                </div>
                              </div>
                              <Badge
                                tone={
                                  detail.coverage === "exact"
                                    ? "success"
                                    : detail.coverage === "partial"
                                      ? "warning"
                                      : "danger"
                                }
                              >
                                {detail.coverage}
                              </Badge>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Missing Block Requests */}
                    {importDetail.synthesis.missingBlockRequests.length > 0 && (
                      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-content">
                          <AlertTriangle className="h-4 w-4 text-warning" />
                          Missing block requests
                        </div>
                        <div className="mt-3 space-y-2">
                          {importDetail.synthesis.missingBlockRequests.map((request) => (
                            <div
                              key={request.requestId}
                              className="rounded-xl border border-warning/30 bg-warning/5 px-3 py-2"
                            >
                              <div className="text-sm font-semibold text-content">{request.sectionType}</div>
                              <div className="mt-1 text-xs text-content-muted">{request.reason}</div>
                              <div className="mt-2 flex flex-wrap gap-2">
                                <Badge tone="neutral">Family: {request.suggestedFamily}</Badge>
                                <Badge tone="neutral">Page: {request.suggestedPageType}</Badge>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Synthesis Preview */}
                    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                      <div className="text-sm font-semibold text-content">Synthesis preview</div>
                      <div className="mt-3 space-y-2 text-xs text-content-muted">
                        <div>
                          <span className="font-semibold text-content">Target family:</span>{" "}
                          {importDetail.synthesis.targetFamily}
                        </div>
                        <div>
                          <span className="font-semibold text-content">Page type:</span>{" "}
                          {importDetail.synthesis.targetPageType}
                        </div>
                        <div>
                          <span className="font-semibold text-content">Puck data:</span>{" "}
                          {Object.keys(importDetail.synthesis.synthesizedPuckData).length > 0
                            ? "Available (structured)"
                            : "Not available"}
                        </div>
                      </div>
                    </div>
                  </>
                )}

                {importDetail.status === "completed" && (
                  <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-content">Save reviewed import as site</div>
                        <div className="text-xs text-content-muted">
                          Creates a new dedicated site runtime record from the adapter-backed page set.
                        </div>
                      </div>
                      {importDetail.savedSiteId ? <Badge tone="success">Already saved</Badge> : null}
                    </div>
                    {saveResult ? (
                      <div className="mt-3 rounded-xl border border-success/30 bg-success/5 px-3 py-3 text-sm text-success">
                        <div className="font-semibold">Saved {saveResult.siteName}</div>
                        <div className="mt-1">
                          Created {saveResult.pageCount} page draft{saveResult.pageCount === 1 ? "" : "s"}
                          {saveResult.entryPageType ? ` with entry page ${formatPageType(saveResult.entryPageType)}.` : "."}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Button size="sm" variant="outline" onClick={() => navigate("/workspaces/sites")}>Open Sites</Button>
                          <Button size="sm" variant="outline" onClick={() => refetchImportDetail()}>Refresh Import</Button>
                        </div>
                      </div>
                    ) : null}
                    {!importDetail.savedSiteId ? (
                      <div className="mt-3 space-y-3">
                        <div className="space-y-1">
                          <label className="text-xs font-semibold text-content">Site name</label>
                          <Input value={saveSiteName} onChange={(e) => setSaveSiteName(e.target.value)} placeholder="Imported site" />
                        </div>
                        <div className="space-y-1">
                          <label className="text-xs font-semibold text-content">Description (optional)</label>
                          <Input value={saveSiteDescription} onChange={(e) => setSaveSiteDescription(e.target.value)} placeholder="What this import represents" />
                        </div>
                        <Button onClick={handleSaveSiteImport} disabled={!saveSiteName.trim() || saveSiteImport.isPending} className="w-full">
                          {saveSiteImport.isPending ? (
                            <>
                              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                              Saving site...
                            </>
                          ) : (
                            <>
                              <Save className="mr-2 h-4 w-4" />
                              Save as New Site
                            </>
                          )}
                        </Button>
                        {saveSiteImport.isError ? (
                          <div className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-3 text-sm text-danger">
                            {readQueryError(saveSiteImport.error, "Failed to save import as site.")}
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <div className="mt-3 rounded-xl border border-border bg-surface-2 px-3 py-3 text-xs text-content-muted">
                        Saved site id: <span className="font-semibold text-content">{importDetail.savedSiteId}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Convert Form */}
                {importDetail.status === "completed" && (
                  <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                    <div className="text-sm font-semibold text-content">Convert to draft</div>
                    <div className="mt-3 space-y-3">
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-content">Name</label>
                        <Input
                          placeholder="My variant"
                          value={convertName}
                          onChange={(e) => setConvertName(e.target.value)}
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-content">Family</label>
                        <Select
                          value={convertFamily}
                          onValueChange={setConvertFamily}
                          options={supportedFamilies}
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-content">Page type</label>
                        <Select
                          value={convertPageType}
                          onValueChange={setConvertPageType}
                          options={supportedPageTypes}
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-content">Review notes (optional)</label>
                        <Input
                          placeholder="Notes for reviewers"
                          value={convertReviewNotes}
                          onChange={(e) => setConvertReviewNotes(e.target.value)}
                        />
                      </div>
                      <Button
                        onClick={handleConvertImport}
                        disabled={!convertName || !selectedSectionIds.length || convertImport.isPending}
                        className="w-full"
                      >
                        {convertImport.isPending ? (
                          <>
                            <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                            Converting...
                          </>
                        ) : (
                          <>
                            <Sparkles className="mr-2 h-4 w-4" />
                            Convert to Draft
                          </>
                        )}
                      </Button>
                      {convertImport.isError && (
                        <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
                          Failed to convert import. Please try again.
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Error State */}
                {importDetail.captureError && (
                  <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-danger">
                      <AlertTriangle className="h-4 w-4" />
                      Capture failed
                    </div>
                    <div className="mt-2 text-sm text-danger">{importDetail.captureError}</div>
                  </div>
                )}
              </>
            ) : (
              <div className="rounded-2xl border border-border bg-surface px-4 py-8 text-center text-sm text-content-muted">
                Loading import details...
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

function VariantMutationPanel({
  variantId,
  workspaceId,
  onVariantGenerated,
}: {
  variantId: string;
  workspaceId?: string;
  onVariantGenerated: () => void;
}) {
  const [selectedPresets, setSelectedPresets] = useState<string[]>([]);
  const [generatedNames, setGeneratedNames] = useState<string[]>([]);

  const { data: variantDetail, isLoading: variantLoading, error: variantError } = useTemplateVariantDetail(
    variantId,
    workspaceId
  );
  const { data: presets = [], isLoading: presetsLoading, error: presetsError } = useVariantPresets(
    variantId,
    workspaceId
  );
  const generateVariants = useGenerateVariants();

  // Reset selection when variant changes
  useEffect(() => {
    setSelectedPresets([]);
    setGeneratedNames([]);
  }, [variantId]);

  const togglePreset = (presetId: string) => {
    setSelectedPresets((prev) =>
      prev.includes(presetId) ? prev.filter((id) => id !== presetId) : [...prev, presetId]
    );
  };

  const handleGenerateVariants = async () => {
    if (!workspaceId || selectedPresets.length === 0) return;

    try {
      await generateVariants.mutateAsync({
        variantId,
        clientId: workspaceId,
        presetIds: selectedPresets,
        generatedNames: generatedNames.length === selectedPresets.length ? generatedNames : undefined,
      });
      onVariantGenerated();
    } catch (err) {
      console.error("Failed to generate variants:", err);
    }
  };

  if (variantLoading || presetsLoading) {
    return (
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="text-sm text-content-muted">Loading variant presets...</div>
      </div>
    );
  }

  if (variantError || presetsError) {
    return (
      <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-4">
        <div className="text-sm text-danger">
          {readQueryError(variantError || presetsError, "Failed to load variant presets.")}
        </div>
      </div>
    );
  }

  const applicablePresets = presets.filter((p) => p.applicable);
  const notApplicablePresets = presets.filter((p) => !p.applicable);

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <div className="text-sm font-semibold text-content">Generate variants</div>
          <div className="text-xs text-content-muted">
            Apply mutation presets to create derived variants.
          </div>
        </div>
        <Wand2 className="h-4 w-4 text-accent" />
      </div>

      {/* Variant Info */}
      {variantDetail && (
        <div className="mt-4 rounded-xl border border-border bg-surface-2 px-3 py-3">
          <div className="text-sm font-semibold text-content">{variantDetail.name}</div>
          <div className="mt-1 text-xs text-content-muted">
            {variantDetail.family} / {formatPageType(variantDetail.pageType)}
          </div>
          {variantDetail.provenance && (() => {
            const provenance = variantDetail.provenance as Record<string, unknown>;
            const sourceType = readProvenanceString(provenance, "sourceType", "source_type");
            const parentVariantName = readProvenanceString(
              provenance,
              "parentVariantName",
              "parent_variant_name"
            );
            const sourceUrl = readProvenanceString(provenance, "sourceUrl", "source_url");
            return (
            <div className="mt-2 text-xs text-content-muted">
              {sourceType === "variant_mutation" ? (
                <span>Derived from: {parentVariantName || "Unknown"}</span>
              ) : (
                <span>Source: {sourceUrl || "Import"}</span>
              )}
            </div>
            );
          })()}
        </div>
      )}

      {/* Applicable Presets */}
      {applicablePresets.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-content">Available presets</div>
          {applicablePresets.map((preset) => (
            <button
              key={preset.presetId}
              type="button"
              onClick={() => togglePreset(preset.presetId)}
              className={cn(
                "w-full rounded-xl border px-3 py-2 text-left transition-colors",
                selectedPresets.includes(preset.presetId)
                  ? "border-accent bg-accent/5"
                  : "border-border bg-surface-2 hover:border-accent/40"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold text-content">{preset.presetLabel}</div>
                  <div className="mt-1 text-xs text-content-muted">{preset.presetDescription}</div>
                </div>
                {selectedPresets.includes(preset.presetId) ? (
                  <CheckCircle2 className="h-4 w-4 text-accent" />
                ) : (
                  <div className="h-4 w-4 rounded-full border border-border" />
                )}
              </div>
              {preset.effects.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {preset.effects.slice(0, 2).map((effect) => (
                    <Badge key={effect} tone="neutral" className="text-[10px]">
                      {effect}
                    </Badge>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Not Applicable Presets */}
      {notApplicablePresets.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-content-muted">Not applicable</div>
          {notApplicablePresets.map((preset) => (
            <div
              key={preset.presetId}
              className="rounded-xl border border-border bg-surface-2/50 px-3 py-2 opacity-60"
            >
              <div className="text-sm font-semibold text-content">{preset.presetLabel}</div>
              <div className="mt-1 text-xs text-content-muted">{preset.notApplicableReason}</div>
            </div>
          ))}
        </div>
      )}

      {/* No presets available */}
      {presets.length === 0 && (
        <div className="mt-4 rounded-xl border border-dashed border-border px-4 py-8 text-sm text-content-muted">
          No mutation presets available for this variant.
        </div>
      )}

      {/* Generate Button */}
      {selectedPresets.length > 0 && (
        <div className="mt-4 space-y-3">
          <Button
            onClick={handleGenerateVariants}
            disabled={generateVariants.isPending || !workspaceId}
            className="w-full"
          >
            {generateVariants.isPending ? (
              <>
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Wand2 className="mr-2 h-4 w-4" />
                Generate {selectedPresets.length} {selectedPresets.length === 1 ? "variant" : "variants"}
              </>
            )}
          </Button>
          {generateVariants.isError && (
            <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
              Failed to generate variants. Please try again.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function GovernancePanel({
  variantId,
  workspaceId,
  onApproved,
}: {
  variantId: string;
  workspaceId?: string;
  onApproved: () => void;
}) {
  const [showConfirm, setShowConfirm] = useState(false);

  const { data: governance, isLoading, error, refetch } = useVariantGovernance(variantId, workspaceId);
  const { data: variantDetail, refetch: refetchVariantDetail } = useTemplateVariantDetail(
    variantId,
    workspaceId
  );
  const approveForPublish = useApproveForPublish();

  // Check if variant is already approved
  const isAlreadyApproved = variantDetail?.status === "approved";

  const handleApprove = async () => {
    if (!workspaceId) return;
    try {
      await approveForPublish.mutateAsync({
        variantId,
        clientId: workspaceId,
      });
      setShowConfirm(false);
      onApproved();
      await Promise.all([refetch(), refetchVariantDetail()]);
    } catch (err) {
      console.error("Failed to approve variant:", err);
    }
  };

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="text-sm text-content-muted">Loading governance report...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-4">
        <div className="text-sm text-danger">
          {readQueryError(error, "Failed to load governance report.")}
        </div>
      </div>
    );
  }

  if (!governance) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <div className="text-sm font-semibold text-content">Governance</div>
          <div className="text-xs text-content-muted">
            Asset validation, style audit, and publish readiness.
          </div>
        </div>
        {isAlreadyApproved ? (
          <Badge tone="success">Approved</Badge>
        ) : (
          <Badge tone={governance.readyForPublish ? "success" : "warning"}>
            {governance.readyForPublish ? "Ready" : "Blocked"}
          </Badge>
        )}
      </div>

      {/* Blockers */}
      {governance.blockers.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-danger">Blockers</div>
          {governance.blockers.map((blocker, idx) => (
            <div key={idx} className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
              {blocker}
            </div>
          ))}
        </div>
      )}

      {/* Warnings */}
      {governance.warnings.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-warning">Warnings</div>
          {governance.warnings.map((warning, idx) => (
            <div key={idx} className="rounded-xl border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-content-muted">
              {warning}
            </div>
          ))}
        </div>
      )}

      {/* Asset Validations */}
      {governance.assetValidations.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-content">Asset references</div>
          {governance.assetValidations.map((asset, idx) => (
            <div key={idx} className="rounded-xl border border-border bg-surface-2 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-content">{asset.publicId}</div>
                <Badge
                  tone={
                    asset.status === "approved"
                      ? "success"
                      : asset.status === "rejected"
                        ? "danger"
                        : asset.status === "pending"
                          ? "warning"
                          : "danger"
                  }
                >
                  {asset.status}
                </Badge>
              </div>
              {asset.blockType && (
                <div className="mt-1 text-xs text-content-muted">
                  {asset.blockType}{asset.blockId ? ` (${asset.blockId})` : ""}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Style Audit */}
      {governance.styleAudit && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-content">Style audit</div>
            <Badge tone={governance.styleAudit.passed ? "success" : "danger"}>
              {governance.styleAudit.passed ? "Passed" : "Failed"}
            </Badge>
          </div>
          {governance.styleAudit.presetName && (
            <div className="text-xs text-content-muted">Preset: {governance.styleAudit.presetName}</div>
          )}
          {governance.styleAudit.findings.length > 0 && (
            <div className="space-y-1">
              {governance.styleAudit.findings.map((finding, idx) => (
                <div
                  key={idx}
                  className={cn(
                    "rounded-lg px-2 py-1 text-xs",
                    finding.status === "pass"
                      ? "bg-success/10 text-success"
                      : "bg-danger/10 text-danger"
                  )}
                >
                  {finding.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* PuckData Structure */}
      {governance.puckDataStructure && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-content">PuckData structure</div>
            <Badge tone={governance.puckDataStructure.valid ? "success" : "danger"}>
              {governance.puckDataStructure.valid ? "Valid" : "Invalid"}
            </Badge>
          </div>
          {governance.puckDataStructure.errors.length > 0 && (
            <div className="space-y-1">
              {governance.puckDataStructure.errors.map((err, idx) => (
                <div key={idx} className="text-xs text-danger">{err}</div>
              ))}
            </div>
          )}
          {governance.puckDataStructure.warnings.length > 0 && (
            <div className="space-y-1">
              {governance.puckDataStructure.warnings.map((warn, idx) => (
                <div key={idx} className="text-xs text-warning">{warn}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Provenance Timeline */}
      {governance.provenanceEvents.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-content">Provenance</div>
          <div className="space-y-2">
            {governance.provenanceEvents.map((event, idx) => (
              <div key={idx} className="rounded-xl border border-border bg-surface-2 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-content">{event.eventType}</div>
                  <div className="text-xs text-content-muted">
                    {new Date(event.timestamp).toLocaleString()}
                  </div>
                </div>
                {event.actor && (
                  <div className="mt-1 text-xs text-content-muted">by {event.actor}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Approve Button - hidden if already approved */}
      {!isAlreadyApproved && governance.readyForPublish && (
        <div className="mt-4 space-y-3">
          {!showConfirm ? (
            <Button onClick={() => setShowConfirm(true)} className="w-full">
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Approve for Publish
            </Button>
          ) : (
            <>
              <div className="rounded-xl border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-content">
                Are you sure you want to approve this variant for publish?
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={handleApprove}
                  disabled={approveForPublish.isPending}
                  className="flex-1"
                >
                  {approveForPublish.isPending ? (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      Approving...
                    </>
                  ) : (
                    "Confirm Approval"
                  )}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowConfirm(false)}
                  disabled={approveForPublish.isPending}
                >
                  Cancel
                </Button>
              </div>
            </>
          )}
          {approveForPublish.isError && (
            <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
              Failed to approve variant. Please try again.
            </div>
          )}
        </div>
      )}

      {/* Already Approved State */}
      {isAlreadyApproved && (
        <div className="mt-4 rounded-xl border border-success/30 bg-success/5 px-3 py-3 text-sm text-success">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>This variant has been approved for publish.</span>
          </div>
        </div>
      )}
    </div>
  );
}
