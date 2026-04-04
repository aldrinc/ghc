import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCreateFunnel,
  useCreateFunnelPage,
  useFunnel,
  useFunnels,
  useGenerateFunnelPageAi,
  useUpdateFunnel,
} from "@/api/funnels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const SITE_IMPORT_HTML_MAX_CHARS = 250_000;
const NEW_FUNNEL_OPTION = "__new__";

type SiteImportTargetTemplate = "sales-pdp" | "pre-sales-listicle";

type SiteImportsCardProps = {
  workspaceId: string;
  activeWorkspaceProduct: { id: string; title: string } | null;
};

type StoredSiteImportState = {
  referenceHtml?: string;
  referenceLabel?: string;
  selectedFunnelId?: string;
  targetTemplateId?: SiteImportTargetTemplate;
  newFunnelName?: string;
  additionalInstructions?: string;
  generateImages?: boolean;
};

function readStoredSiteImportState(key: string | null): StoredSiteImportState | null {
  if (!key) return null;
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as StoredSiteImportState;
  } catch {
    return null;
  }
}

function writeStoredSiteImportState(key: string | null, state: StoredSiteImportState): void {
  if (!key) return;
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify(state));
  } catch {
    // Ignore storage errors.
  }
}

function defaultImportedFunnelName(productTitle: string): string {
  const normalized = productTitle.trim();
  if (!normalized) return "Imported Template Funnel";
  return `${normalized} Imported Template`;
}

function targetTemplateLabel(templateId: SiteImportTargetTemplate): string {
  return templateId === "sales-pdp" ? "Sales page" : "Pre-sales page";
}

function targetPageName(templateId: SiteImportTargetTemplate): string {
  return templateId === "sales-pdp" ? "Sales Page" : "Pre-Sales Page";
}

function buildGenerationPrompt(args: {
  productTitle: string;
  templateId: SiteImportTargetTemplate;
  additionalInstructions: string;
}): string {
  const productTitle = args.productTitle.trim() || "the active product";
  const basePrompt =
    args.templateId === "sales-pdp"
      ? `Generate a sales page for ${productTitle}. Use the imported HTML as the primary structure and persuasion template, then rebuild it for the product inside the supported sales-pdp component system.`
      : `Generate a pre-sales listicle page for ${productTitle}. Use the imported HTML as the primary structure and persuasion template, then rebuild it for the product inside the supported pre-sales-listicle component system.`;
  const instructions = args.additionalInstructions.trim();
  if (!instructions) return basePrompt;
  return `${basePrompt}\n\nAdditional instructions:\n${instructions}`;
}

export function SiteImportsCard({ workspaceId, activeWorkspaceProduct }: SiteImportsCardProps) {
  const navigate = useNavigate();
  const createFunnel = useCreateFunnel();
  const createPage = useCreateFunnelPage();
  const updateFunnel = useUpdateFunnel();
  const generateFunnelPageAi = useGenerateFunnelPageAi();
  const storageKey = activeWorkspaceProduct
    ? `site-imports:${workspaceId}:${activeWorkspaceProduct.id}`
    : null;
  const hasRestoredRef = useRef(false);
  const htmlFileInputRef = useRef<HTMLInputElement | null>(null);

  const [referenceHtml, setReferenceHtml] = useState("");
  const [referenceLabel, setReferenceLabel] = useState<string | null>(null);
  const [targetTemplateId, setTargetTemplateId] = useState<SiteImportTargetTemplate>("sales-pdp");
  const [selectedFunnelId, setSelectedFunnelId] = useState(NEW_FUNNEL_OPTION);
  const [newFunnelName, setNewFunnelName] = useState("");
  const [additionalInstructions, setAdditionalInstructions] = useState("");
  const [generateImages, setGenerateImages] = useState(true);

  const trimmedReferenceHtml = referenceHtml.trim();
  const selectedExistingFunnelId =
    selectedFunnelId && selectedFunnelId !== NEW_FUNNEL_OPTION ? selectedFunnelId : undefined;

  const { data: productFunnels = [] } = useFunnels(
    activeWorkspaceProduct?.id ? { clientId: workspaceId, productId: activeWorkspaceProduct.id } : undefined,
  );
  const { data: selectedFunnelDetail, isLoading: isLoadingSelectedFunnel } = useFunnel(selectedExistingFunnelId);

  useEffect(() => {
    hasRestoredRef.current = false;
    const stored = readStoredSiteImportState(storageKey);
    if (stored) {
      setReferenceHtml(typeof stored.referenceHtml === "string" ? stored.referenceHtml : "");
      setReferenceLabel(typeof stored.referenceLabel === "string" ? stored.referenceLabel : null);
      setTargetTemplateId(
        stored.targetTemplateId === "pre-sales-listicle" ? "pre-sales-listicle" : "sales-pdp",
      );
      setSelectedFunnelId(
        typeof stored.selectedFunnelId === "string" && stored.selectedFunnelId.trim()
          ? stored.selectedFunnelId
          : NEW_FUNNEL_OPTION,
      );
      setNewFunnelName(typeof stored.newFunnelName === "string" ? stored.newFunnelName : "");
      setAdditionalInstructions(
        typeof stored.additionalInstructions === "string" ? stored.additionalInstructions : "",
      );
      setGenerateImages(typeof stored.generateImages === "boolean" ? stored.generateImages : true);
    } else {
      setReferenceHtml("");
      setReferenceLabel(null);
      setTargetTemplateId("sales-pdp");
      setSelectedFunnelId(NEW_FUNNEL_OPTION);
      setNewFunnelName(activeWorkspaceProduct ? defaultImportedFunnelName(activeWorkspaceProduct.title) : "");
      setAdditionalInstructions("");
      setGenerateImages(true);
    }
    hasRestoredRef.current = true;
  }, [activeWorkspaceProduct, storageKey]);

  useEffect(() => {
    if (!storageKey || !hasRestoredRef.current) return;
    writeStoredSiteImportState(storageKey, {
      referenceHtml,
      referenceLabel: referenceLabel ?? undefined,
      targetTemplateId,
      selectedFunnelId,
      newFunnelName,
      additionalInstructions,
      generateImages,
    });
  }, [
    additionalInstructions,
    generateImages,
    newFunnelName,
    referenceHtml,
    referenceLabel,
    selectedFunnelId,
    storageKey,
    targetTemplateId,
  ]);

  const funnelOptions = useMemo(
    () => [
      { label: "Create new funnel", value: NEW_FUNNEL_OPTION },
      ...productFunnels.map((funnel) => ({ label: funnel.name, value: funnel.id })),
    ],
    [productFunnels],
  );

  useEffect(() => {
    if (selectedFunnelId === NEW_FUNNEL_OPTION) return;
    if (productFunnels.some((funnel) => funnel.id === selectedFunnelId)) return;
    setSelectedFunnelId(NEW_FUNNEL_OPTION);
  }, [productFunnels, selectedFunnelId]);

  const targetPage = useMemo(() => {
    if (!selectedFunnelDetail?.pages?.length) return null;
    return (
      selectedFunnelDetail.pages
        .slice()
        .sort((a, b) => a.ordering - b.ordering)
        .find((page) => page.template_id === targetTemplateId) || null
    );
  }, [selectedFunnelDetail?.pages, targetTemplateId]);

  const nextActionLabel = useMemo(() => {
    if (!activeWorkspaceProduct) return "Select a product to generate a page from an imported template.";
    if (selectedFunnelId === NEW_FUNNEL_OPTION) {
      return `A new funnel and ${targetTemplateLabel(targetTemplateId).toLowerCase()} will be created.`;
    }
    if (isLoadingSelectedFunnel) return "Loading the selected funnel pages.";
    if (targetPage) return `The imported HTML will regenerate the draft for "${targetPage.name}".`;
    return `A new ${targetTemplateLabel(targetTemplateId).toLowerCase()} will be created in the selected funnel.`;
  }, [activeWorkspaceProduct, isLoadingSelectedFunnel, selectedFunnelId, targetPage, targetTemplateId]);

  const isBusy =
    createFunnel.isPending ||
    createPage.isPending ||
    updateFunnel.isPending ||
    generateFunnelPageAi.isPending;

  const handleReferenceHtmlSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > SITE_IMPORT_HTML_MAX_CHARS) {
      toast.error(`HTML reference files must be ${SITE_IMPORT_HTML_MAX_CHARS.toLocaleString()} characters or smaller.`);
      return;
    }

    const readHtml = async () => {
      try {
        const text = await file.text();
        const trimmed = text.trim();
        if (!trimmed) throw new Error("Selected HTML file is empty.");
        if (trimmed.length > SITE_IMPORT_HTML_MAX_CHARS) {
          throw new Error(
            `HTML reference exceeds the ${SITE_IMPORT_HTML_MAX_CHARS.toLocaleString()} character limit.`,
          );
        }
        setReferenceHtml(trimmed);
        setReferenceLabel(file.name);
        toast.success("HTML template loaded");
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to read HTML reference file";
        toast.error(message);
      }
    };

    void readHtml();
  };

  const handleGenerateFromImport = async () => {
    if (!activeWorkspaceProduct) {
      toast.error("Select a product before generating a funnel page from imported HTML.");
      return;
    }
    if (!trimmedReferenceHtml) {
      toast.error("Import HTML before generating a funnel page.");
      return;
    }
    if (trimmedReferenceHtml.length > SITE_IMPORT_HTML_MAX_CHARS) {
      toast.error(`HTML reference exceeds the ${SITE_IMPORT_HTML_MAX_CHARS.toLocaleString()} character limit.`);
      return;
    }
    if (selectedFunnelId !== NEW_FUNNEL_OPTION && isLoadingSelectedFunnel) {
      toast.error("Wait for the selected funnel to finish loading.");
      return;
    }

    const resolvedFunnel =
      selectedFunnelId === NEW_FUNNEL_OPTION
        ? await createFunnel.mutateAsync({
            clientId: workspaceId,
            productId: activeWorkspaceProduct.id,
            name: newFunnelName.trim() || defaultImportedFunnelName(activeWorkspaceProduct.title),
            description: "Generated from an imported HTML template.",
          })
        : null;

    const funnelId = resolvedFunnel?.id || selectedExistingFunnelId;
    if (!funnelId) {
      toast.error("Select a funnel or create a new one before generating.");
      return;
    }

    if (resolvedFunnel) {
      setSelectedFunnelId(resolvedFunnel.id);
    }

    const page = targetPage
      ? targetPage
      : (
          await createPage.mutateAsync({
            funnelId,
            name: targetPageName(targetTemplateId),
            templateId: targetTemplateId,
          })
        ).page;

    if (resolvedFunnel || !selectedFunnelDetail?.entry_page_id) {
      await updateFunnel.mutateAsync({
        funnelId,
        payload: { entryPageId: page.id },
      });
    }

    await generateFunnelPageAi.mutateAsync({
      funnelId,
      pageId: page.id,
      prompt: buildGenerationPrompt({
        productTitle: activeWorkspaceProduct.title,
        templateId: targetTemplateId,
        additionalInstructions,
      }),
      messages: [],
      referenceHtml: trimmedReferenceHtml,
      referenceLabel: referenceLabel ?? "pasted-html",
      referenceHtmlMode: "template",
      requireLatestStrategyCopy: true,
      generateImages,
    });

    navigate(`/research/funnels/${funnelId}/pages/${page.id}`);
  };

  return (
    <div className="ds-card ds-card--md space-y-4">
      <div>
        <div className="text-sm font-semibold text-content">Site imports</div>
        <div className="text-xs text-content-muted">
          Import HTML here, choose sales or pre-sales, and generate the funnel page directly from this template using the latest strategy copy.
        </div>
      </div>

      {!activeWorkspaceProduct ? (
        <div className="rounded-md border border-border bg-surface-2 p-3 text-xs text-content-muted">
          Select an active product to import HTML and generate funnel pages from this Sites workflow.
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label className="text-xs font-medium text-content">Target page</label>
          <Select
            value={targetTemplateId}
            onValueChange={(value) => setTargetTemplateId(value as SiteImportTargetTemplate)}
            options={[
              { label: "Sales page", value: "sales-pdp" },
              { label: "Pre-sales page", value: "pre-sales-listicle" },
            ]}
            disabled={!activeWorkspaceProduct || isBusy}
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-content">Funnel</label>
          <Select
            value={selectedFunnelId}
            onValueChange={setSelectedFunnelId}
            options={funnelOptions}
            disabled={!activeWorkspaceProduct || isBusy}
          />
        </div>
      </div>

      {selectedFunnelId === NEW_FUNNEL_OPTION ? (
        <div className="space-y-1">
          <label className="text-xs font-medium text-content">New funnel name</label>
          <Input
            value={newFunnelName}
            onChange={(event) => setNewFunnelName(event.target.value)}
            placeholder={activeWorkspaceProduct ? defaultImportedFunnelName(activeWorkspaceProduct.title) : "Imported Template Funnel"}
            disabled={!activeWorkspaceProduct || isBusy}
          />
        </div>
      ) : null}

      <div className="space-y-2 rounded-md border border-divider bg-surface-2 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs font-semibold text-content">Imported HTML template</div>
            <div className="text-[11px] text-content-muted">
              Paste or upload the HTML export you want the funnel agent to use as reference. This flow requires the latest strategy copy outputs for the selected product.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => htmlFileInputRef.current?.click()}
              disabled={!activeWorkspaceProduct || isBusy}
            >
              Upload HTML
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setReferenceHtml("");
                setReferenceLabel(null);
              }}
              disabled={!referenceHtml || isBusy}
            >
              Clear HTML
            </Button>
          </div>
        </div>

        <input
          ref={htmlFileInputRef}
          className="hidden"
          type="file"
          accept="text/html,.html,.htm,text/plain"
          onChange={handleReferenceHtmlSelect}
        />

        <textarea
          rows={8}
          value={referenceHtml}
          onChange={(event) => {
            const nextValue = event.target.value;
            setReferenceHtml(nextValue);
            setReferenceLabel(nextValue.trim() ? "pasted-html" : null);
          }}
          placeholder="Paste full HTML here, or upload a .html file."
          disabled={!activeWorkspaceProduct || isBusy}
          className={cn(
            "min-h-[180px] w-full resize-y rounded-md border border-border bg-surface px-3 py-2 font-mono text-xs text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface placeholder:text-content-muted disabled:cursor-not-allowed disabled:opacity-60",
          )}
        />

        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-content-muted">
          <span>Source: {referenceLabel || "none"}</span>
          <span>
            {referenceHtml.length.toLocaleString()} / {SITE_IMPORT_HTML_MAX_CHARS.toLocaleString()} characters
          </span>
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium text-content">Additional instructions</label>
        <textarea
          rows={4}
          value={additionalInstructions}
          onChange={(event) => setAdditionalInstructions(event.target.value)}
          placeholder="Optional: describe how you want this sales or pre-sales page adapted."
          disabled={!activeWorkspaceProduct || isBusy}
          className={cn(
            "min-h-[120px] w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface placeholder:text-content-muted disabled:cursor-not-allowed disabled:opacity-60",
          )}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-surface-2 p-3">
        <div className="space-y-1">
          <div className="text-xs font-semibold text-content">Generation target</div>
          <div className="text-xs text-content-muted">{nextActionLabel}</div>
          <div className="text-[11px] text-content-muted">
            Latest strategy copy is required and will drive the sales or pre-sales messaging before the imported HTML influences structure.
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-content-muted">
          <input
            type="checkbox"
            checked={generateImages}
            onChange={(event) => setGenerateImages(event.target.checked)}
            disabled={!activeWorkspaceProduct || isBusy}
            className="size-4 rounded border-border text-primary focus:ring-2 focus:ring-primary"
          />
          Generate images
        </label>
      </div>

      <Button
        onClick={() => void handleGenerateFromImport()}
        disabled={!activeWorkspaceProduct || !trimmedReferenceHtml || isBusy || (selectedFunnelId !== NEW_FUNNEL_OPTION && isLoadingSelectedFunnel)}
      >
        {isBusy ? `Generating ${targetTemplateLabel(targetTemplateId).toLowerCase()}…` : `Generate ${targetTemplateLabel(targetTemplateId).toLowerCase()}`}
      </Button>
    </div>
  );
}
