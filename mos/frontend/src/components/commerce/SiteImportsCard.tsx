import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useApiClient } from "@/api/client";
import { useFunnel, useFunnels } from "@/api/funnels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { Funnel, FunnelPage } from "@/types/funnels";

import {
  buildSiteImportBatchItem,
  defaultPairedSalesPageName,
  defaultPairedSalesPageSlug,
  defaultSharedSalesPageName,
  defaultSharedSalesPageSlug,
  defaultSiteImportPageName,
  makeUniqueSiteImportSlug,
  type SiteImportBatchItem,
  type SiteImportSalesWiringMode,
  type SiteImportSharedSalesTarget,
  type SiteImportTargetTemplate,
} from "./siteImportBatch";

const SITE_IMPORT_HTML_MAX_CHARS = 250_000;
const NEW_FUNNEL_OPTION = "__new__";

type SiteImportsCardProps = {
  workspaceId: string;
  activeWorkspaceProduct: { id: string; title: string } | null;
};

type StoredSiteImportItemState = {
  referenceHtml?: string;
  referenceLabel?: string;
  pageName?: string;
  slug?: string;
};

type StoredSiteImportState = {
  referenceHtml?: string;
  referenceLabel?: string;
  draftReferenceHtml?: string;
  draftReferenceLabel?: string;
  importItems?: StoredSiteImportItemState[];
  selectedFunnelId?: string;
  targetTemplateId?: SiteImportTargetTemplate;
  newFunnelName?: string;
  additionalInstructions?: string;
  generateImages?: boolean;
  salesWiringMode?: SiteImportSalesWiringMode;
  sharedSalesTarget?: SiteImportSharedSalesTarget;
  sharedSalesPageId?: string;
  sharedSalesPageName?: string;
  sharedSalesPageSlug?: string;
};

let nextSiteImportItemSequence = 0;

function nextSiteImportItemId(): string {
  nextSiteImportItemSequence += 1;
  return `site-import-${nextSiteImportItemSequence}`;
}

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
      ? `Generate a sales page for ${productTitle}. Preserve the imported HTML exactly and only inject the correct product and strategy copy into the existing template.`
      : `Generate a pre-sales listicle page for ${productTitle}. Preserve the imported HTML exactly and only inject the correct product and strategy copy into the existing template.`;
  const instructions = args.additionalInstructions.trim();
  if (!instructions) return basePrompt;
  return `${basePrompt}\n\nAdditional instructions:\n${instructions}`;
}

function getApiErrorMessage(error: unknown, fallbackMessage: string): string {
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
    return error.message;
  }
  return fallbackMessage;
}

function formatCount(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function restoreImportItems(items: unknown): SiteImportBatchItem[] {
  if (!Array.isArray(items)) return [];
  const restored: SiteImportBatchItem[] = [];
  const usedSlugs = new Set<string>();
  for (const entry of items) {
    if (!entry || typeof entry !== "object") continue;
    const stored = entry as StoredSiteImportItemState;
    const referenceHtml = typeof stored.referenceHtml === "string" ? stored.referenceHtml.trim() : "";
    const referenceLabel =
      typeof stored.referenceLabel === "string" && stored.referenceLabel.trim()
        ? stored.referenceLabel.trim()
        : "";
    if (!referenceHtml || !referenceLabel) continue;
    const pageName =
      typeof stored.pageName === "string" && stored.pageName.trim()
        ? stored.pageName.trim()
        : defaultSiteImportPageName(referenceLabel);
    const desiredSlug =
      typeof stored.slug === "string" && stored.slug.trim() ? stored.slug.trim() : pageName;
    const slug = makeUniqueSiteImportSlug(desiredSlug, usedSlugs);
    usedSlugs.add(slug);
    restored.push({
      id: nextSiteImportItemId(),
      referenceHtml,
      referenceLabel,
      pageName,
      slug,
    });
  }
  return restored;
}

function summarizeGenerationTarget(args: {
  activeWorkspaceProduct: { id: string; title: string } | null;
  importCount: number;
  selectedFunnelId: string;
  isLoadingSelectedFunnel: boolean;
  targetTemplateId: SiteImportTargetTemplate;
  reusingExistingTargetPageName: string | null;
  salesWiringMode: SiteImportSalesWiringMode;
  sharedSalesTarget: SiteImportSharedSalesTarget;
  sharedSalesPageName: string;
  sharedExistingSalesPageName: string | null;
}): string {
  if (!args.activeWorkspaceProduct) {
    return "Select a product to generate funnel pages from imported HTML.";
  }
  if (!args.importCount) {
    return "Upload one or more HTML files, or paste HTML and add it to the queue.";
  }
  if (args.selectedFunnelId !== NEW_FUNNEL_OPTION && args.isLoadingSelectedFunnel) {
    return "Loading the selected funnel pages.";
  }
  if (args.reusingExistingTargetPageName) {
    return `The imported HTML will regenerate the draft for "${args.reusingExistingTargetPageName}".`;
  }

  const targetPrefix =
    args.selectedFunnelId === NEW_FUNNEL_OPTION ? "A new funnel will be created with" : "This import will create";
  const importLabel = targetTemplateLabel(args.targetTemplateId).toLowerCase();
  if (args.targetTemplateId === "sales-pdp") {
    return `${targetPrefix} ${formatCount(args.importCount, importLabel)}.`;
  }
  if (args.salesWiringMode === "shared") {
    if (args.sharedSalesTarget === "existing" && args.sharedExistingSalesPageName) {
      return `${targetPrefix} ${formatCount(args.importCount, importLabel)} wired to "${args.sharedExistingSalesPageName}".`;
    }
    const sharedName = args.sharedSalesPageName.trim() || defaultSharedSalesPageName();
    return `${targetPrefix} 1 shared sales page ("${sharedName}") and ${formatCount(args.importCount, importLabel)}.`;
  }
  if (args.salesWiringMode === "paired") {
    return `${targetPrefix} ${formatCount(args.importCount, "sales page")} and ${formatCount(args.importCount, importLabel)}.`;
  }
  return `${targetPrefix} ${formatCount(args.importCount, importLabel)} with no sales-page wiring.`;
}

export function SiteImportsCard({ workspaceId, activeWorkspaceProduct }: SiteImportsCardProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { post, request } = useApiClient();
  const storageKey = activeWorkspaceProduct
    ? `site-imports:${workspaceId}:${activeWorkspaceProduct.id}`
    : null;
  const hasRestoredRef = useRef(false);
  const htmlFileInputRef = useRef<HTMLInputElement | null>(null);

  const [draftReferenceHtml, setDraftReferenceHtml] = useState("");
  const [draftReferenceLabel, setDraftReferenceLabel] = useState<string | null>(null);
  const [importItems, setImportItems] = useState<SiteImportBatchItem[]>([]);
  const [targetTemplateId, setTargetTemplateId] = useState<SiteImportTargetTemplate>("sales-pdp");
  const [selectedFunnelId, setSelectedFunnelId] = useState(NEW_FUNNEL_OPTION);
  const [newFunnelName, setNewFunnelName] = useState("");
  const [additionalInstructions, setAdditionalInstructions] = useState("");
  const [generateImages, setGenerateImages] = useState(true);
  const [salesWiringMode, setSalesWiringMode] = useState<SiteImportSalesWiringMode>("none");
  const [sharedSalesTarget, setSharedSalesTarget] = useState<SiteImportSharedSalesTarget>("new");
  const [sharedSalesPageId, setSharedSalesPageId] = useState("");
  const [sharedSalesPageName, setSharedSalesPageName] = useState(defaultSharedSalesPageName());
  const [sharedSalesPageSlug, setSharedSalesPageSlug] = useState(defaultSharedSalesPageSlug());
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatusLabel, setSubmitStatusLabel] = useState<string | null>(null);

  const trimmedDraftReferenceHtml = draftReferenceHtml.trim();
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
      setDraftReferenceHtml(
        typeof stored.draftReferenceHtml === "string"
          ? stored.draftReferenceHtml
          : typeof stored.referenceHtml === "string"
            ? stored.referenceHtml
            : "",
      );
      setDraftReferenceLabel(
        typeof stored.draftReferenceLabel === "string"
          ? stored.draftReferenceLabel
          : typeof stored.referenceLabel === "string"
            ? stored.referenceLabel
            : null,
      );
      setImportItems(restoreImportItems(stored.importItems));
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
      setSalesWiringMode(
        stored.salesWiringMode === "shared" || stored.salesWiringMode === "paired"
          ? stored.salesWiringMode
          : "none",
      );
      setSharedSalesTarget(stored.sharedSalesTarget === "existing" ? "existing" : "new");
      setSharedSalesPageId(typeof stored.sharedSalesPageId === "string" ? stored.sharedSalesPageId : "");
      setSharedSalesPageName(
        typeof stored.sharedSalesPageName === "string"
          ? stored.sharedSalesPageName
          : defaultSharedSalesPageName(),
      );
      setSharedSalesPageSlug(
        typeof stored.sharedSalesPageSlug === "string"
          ? stored.sharedSalesPageSlug
          : defaultSharedSalesPageSlug(),
      );
    } else {
      setDraftReferenceHtml("");
      setDraftReferenceLabel(null);
      setImportItems([]);
      setTargetTemplateId("sales-pdp");
      setSelectedFunnelId(NEW_FUNNEL_OPTION);
      setNewFunnelName(activeWorkspaceProduct ? defaultImportedFunnelName(activeWorkspaceProduct.title) : "");
      setAdditionalInstructions("");
      setGenerateImages(true);
      setSalesWiringMode("none");
      setSharedSalesTarget("new");
      setSharedSalesPageId("");
      setSharedSalesPageName(defaultSharedSalesPageName());
      setSharedSalesPageSlug(defaultSharedSalesPageSlug());
    }
    hasRestoredRef.current = true;
  }, [activeWorkspaceProduct, storageKey]);

  useEffect(() => {
    if (!storageKey || !hasRestoredRef.current) return;
    writeStoredSiteImportState(storageKey, {
      draftReferenceHtml,
      draftReferenceLabel: draftReferenceLabel ?? undefined,
      importItems: importItems.map((item) => ({
        referenceHtml: item.referenceHtml,
        referenceLabel: item.referenceLabel,
        pageName: item.pageName,
        slug: item.slug,
      })),
      selectedFunnelId,
      targetTemplateId,
      newFunnelName,
      additionalInstructions,
      generateImages,
      salesWiringMode,
      sharedSalesTarget,
      sharedSalesPageId,
      sharedSalesPageName,
      sharedSalesPageSlug,
    });
  }, [
    additionalInstructions,
    draftReferenceHtml,
    draftReferenceLabel,
    generateImages,
    importItems,
    newFunnelName,
    salesWiringMode,
    selectedFunnelId,
    sharedSalesPageId,
    sharedSalesPageName,
    sharedSalesPageSlug,
    sharedSalesTarget,
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

  const salesPages = useMemo(
    () =>
      (selectedFunnelDetail?.pages ?? [])
        .filter((page) => page.template_id === "sales-pdp")
        .slice()
        .sort((a, b) => a.ordering - b.ordering),
    [selectedFunnelDetail?.pages],
  );

  useEffect(() => {
    if (selectedFunnelId === NEW_FUNNEL_OPTION || salesPages.length === 0) {
      if (sharedSalesTarget === "existing") {
        setSharedSalesTarget("new");
      }
      if (sharedSalesPageId) {
        setSharedSalesPageId("");
      }
      return;
    }
    if (!salesPages.some((page) => page.id === sharedSalesPageId)) {
      setSharedSalesPageId(salesPages[0]?.id ?? "");
    }
  }, [salesPages, selectedFunnelId, sharedSalesPageId, sharedSalesTarget]);

  const importCount = importItems.length || (trimmedDraftReferenceHtml ? 1 : 0);
  const hasDraftConflict = importItems.length > 0 && Boolean(trimmedDraftReferenceHtml);
  const canReuseExistingTargetPage = Boolean(
    selectedExistingFunnelId &&
      targetPage &&
      !importItems.length &&
      trimmedDraftReferenceHtml &&
      (targetTemplateId === "sales-pdp" || salesWiringMode === "none"),
  );
  const sharedExistingSalesPageName = salesPages.find((page) => page.id === sharedSalesPageId)?.name || null;

  const nextActionLabel = useMemo(
    () =>
      summarizeGenerationTarget({
        activeWorkspaceProduct,
        importCount,
        selectedFunnelId,
        isLoadingSelectedFunnel,
        targetTemplateId,
        reusingExistingTargetPageName: canReuseExistingTargetPage ? targetPage?.name || null : null,
        salesWiringMode,
        sharedSalesTarget,
        sharedSalesPageName,
        sharedExistingSalesPageName,
      }),
    [
      activeWorkspaceProduct,
      canReuseExistingTargetPage,
      importCount,
      isLoadingSelectedFunnel,
      selectedFunnelId,
      salesWiringMode,
      sharedExistingSalesPageName,
      sharedSalesPageName,
      sharedSalesTarget,
      targetPage?.name,
      targetTemplateId,
    ],
  );

  const salesPageOptions = useMemo(
    () =>
      salesPages.map((page) => ({
        label: `${page.name} (${page.slug})`,
        value: page.id,
      })),
    [salesPages],
  );

  const isBusy = isSubmitting;

  const resetDraftComposer = () => {
    setDraftReferenceHtml("");
    setDraftReferenceLabel(null);
  };

  const buildDraftImportItem = (usedSlugs: Iterable<string>): SiteImportBatchItem => {
    const referenceLabel = draftReferenceLabel?.trim() || targetPageName(targetTemplateId);
    return buildSiteImportBatchItem({
      id: nextSiteImportItemId(),
      referenceHtml: trimmedDraftReferenceHtml,
      referenceLabel,
      usedSlugs,
    });
  };

  const handleReferenceHtmlSelect = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;

    const readHtmlFiles = async () => {
      const usedSlugs = new Set<string>([
        ...importItems.map((item) => item.slug),
        ...(selectedFunnelDetail?.pages ?? []).map((page) => page.slug),
      ]);
      const nextItems: SiteImportBatchItem[] = [];

      for (const file of files) {
        try {
          const text = await file.text();
          const trimmed = text.trim();
          if (!trimmed) {
            throw new Error(`"${file.name}" is empty.`);
          }
          if (trimmed.length > SITE_IMPORT_HTML_MAX_CHARS) {
            throw new Error(
              `"${file.name}" exceeds the ${SITE_IMPORT_HTML_MAX_CHARS.toLocaleString()} character limit.`,
            );
          }
          const item = buildSiteImportBatchItem({
            id: nextSiteImportItemId(),
            referenceHtml: trimmed,
            referenceLabel: file.name,
            usedSlugs,
          });
          usedSlugs.add(item.slug);
          nextItems.push(item);
        } catch (error) {
          toast.error(getApiErrorMessage(error, `Failed to read "${file.name}".`));
        }
      }

      if (!nextItems.length) return;
      setImportItems((current) => [...current, ...nextItems]);
      toast.success(nextItems.length === 1 ? "1 HTML template queued" : `${nextItems.length} HTML templates queued`);
    };

    void readHtmlFiles();
  };

  const handleAddDraftImport = () => {
    if (!trimmedDraftReferenceHtml) {
      toast.error("Paste HTML before adding it to the queue.");
      return;
    }
    if (trimmedDraftReferenceHtml.length > SITE_IMPORT_HTML_MAX_CHARS) {
      toast.error(`HTML reference exceeds the ${SITE_IMPORT_HTML_MAX_CHARS.toLocaleString()} character limit.`);
      return;
    }
    const item = buildDraftImportItem([
      ...importItems.map((current) => current.slug),
      ...(selectedFunnelDetail?.pages ?? []).map((page) => page.slug),
    ]);
    setImportItems((current) => [...current, item]);
    resetDraftComposer();
    toast.success("HTML template queued");
  };

  const handleGenerateFromImport = async () => {
    if (!activeWorkspaceProduct) {
      toast.error("Select a product before generating funnel pages from imported HTML.");
      return;
    }
    if (!importCount) {
      toast.error("Import HTML before generating funnel pages.");
      return;
    }
    if (selectedFunnelId !== NEW_FUNNEL_OPTION && isLoadingSelectedFunnel) {
      toast.error("Wait for the selected funnel to finish loading.");
      return;
    }
    if (hasDraftConflict) {
      toast.error("Add or clear the pasted HTML before generating so the queue is unambiguous.");
      return;
    }
    if (
      targetTemplateId === "pre-sales-listicle" &&
      salesWiringMode === "shared" &&
      sharedSalesTarget === "existing" &&
      !sharedSalesPageId
    ) {
      toast.error("Select the shared sales page before generating.");
      return;
    }

    const queuedItems = importItems.length
      ? importItems.map((item) => ({
          ...item,
          referenceHtml: item.referenceHtml.trim(),
          pageName: item.pageName.trim(),
          slug: item.slug.trim(),
        }))
      : trimmedDraftReferenceHtml
        ? [buildDraftImportItem((selectedFunnelDetail?.pages ?? []).map((page) => page.slug))]
        : [];

    const invalidItem = queuedItems.find(
      (item) => !item.referenceHtml || item.referenceHtml.length > SITE_IMPORT_HTML_MAX_CHARS || !item.pageName,
    );
    if (invalidItem) {
      toast.error(`Review the queued HTML for "${invalidItem.referenceLabel}" before generating.`);
      return;
    }

    let touchedFunnelId: string | null = null;
    let completedImports = 0;

    setIsSubmitting(true);
    setSubmitStatusLabel("Preparing import…");

    try {
      const legacyReusePage = canReuseExistingTargetPage && targetPage && queuedItems.length === 1 ? targetPage : null;

      const resolvedFunnel =
        selectedFunnelId === NEW_FUNNEL_OPTION
          ? await post<Funnel>("/funnels", {
              clientId: workspaceId,
              productId: activeWorkspaceProduct.id,
              name: newFunnelName.trim() || defaultImportedFunnelName(activeWorkspaceProduct.title),
              description: "Generated from imported HTML templates.",
            })
          : null;

      const funnelId = resolvedFunnel?.id || selectedExistingFunnelId;
      if (!funnelId) {
        toast.error("Select a funnel or create a new one before generating.");
        return;
      }

      touchedFunnelId = funnelId;

      if (resolvedFunnel) {
        setSelectedFunnelId(resolvedFunnel.id);
      }

      const entryPageIdBeforeImport = resolvedFunnel ? null : selectedFunnelDetail?.entry_page_id ?? null;
      let firstGeneratedPageId: string | null = null;
      let createdSalesPageCount = 0;
      let sharedSalesPageTargetId: string | null = null;
      let createdSharedSalesPageName: string | null = null;
      let workingPages = (resolvedFunnel ? [] : selectedFunnelDetail?.pages ?? [])
        .slice()
        .sort((a, b) => a.ordering - b.ordering);

      if (legacyReusePage) {
        setSubmitStatusLabel(`Generating ${legacyReusePage.name}…`);
        await post(`/funnels/${funnelId}/pages/${legacyReusePage.id}/ai/generate`, {
          prompt: buildGenerationPrompt({
            productTitle: activeWorkspaceProduct.title,
            templateId: targetTemplateId,
            additionalInstructions,
          }),
          messages: [],
          referenceHtml: queuedItems[0].referenceHtml,
          referenceLabel: queuedItems[0].referenceLabel,
          referenceHtmlMode: "template",
          requireLatestStrategyCopy: true,
          generateImages,
        });
        completedImports = 1;
        if (resolvedFunnel || !entryPageIdBeforeImport) {
          setSubmitStatusLabel("Setting funnel entry page…");
          await request<Funnel>(`/funnels/${funnelId}`, {
            method: "PATCH",
            body: JSON.stringify({ entryPageId: legacyReusePage.id }),
          });
        }
        await queryClient.invalidateQueries({ queryKey: ["funnels"] });
        resetDraftComposer();
        toast.success(`Regenerated "${legacyReusePage.name}" from imported HTML.`);
        navigate(`/research/funnels/${funnelId}/pages/${legacyReusePage.id}`);
        return;
      }

      if (targetTemplateId === "pre-sales-listicle" && salesWiringMode === "shared") {
        if (sharedSalesTarget === "existing") {
          sharedSalesPageTargetId = sharedSalesPageId;
        } else {
          const desiredName = sharedSalesPageName.trim() || defaultSharedSalesPageName();
          const desiredSlug = sharedSalesPageSlug.trim() || defaultSharedSalesPageSlug();
          setSubmitStatusLabel("Creating shared sales page…");
          const response = await post<{ page: FunnelPage }>(`/funnels/${funnelId}/pages`, {
            name: desiredName,
            templateId: "sales-pdp",
            slug: desiredSlug,
          });
          sharedSalesPageTargetId = response.page.id;
          createdSharedSalesPageName = response.page.name;
          createdSalesPageCount += 1;
          workingPages = [...workingPages, response.page];
        }
      }

      for (const [index, item] of queuedItems.entries()) {
        let nextPageId: string | null = null;

        if (targetTemplateId === "pre-sales-listicle" && salesWiringMode === "shared") {
          nextPageId = sharedSalesPageTargetId;
        }

        if (targetTemplateId === "pre-sales-listicle" && salesWiringMode === "paired") {
          const desiredSalesSlug = makeUniqueSiteImportSlug(
            defaultPairedSalesPageSlug(item.slug || item.pageName),
            workingPages.map((page) => page.slug),
          );
          setSubmitStatusLabel(`Creating sales page ${index + 1} of ${queuedItems.length}…`);
          const response = await post<{ page: FunnelPage }>(`/funnels/${funnelId}/pages`, {
            name: defaultPairedSalesPageName(item.pageName),
            templateId: "sales-pdp",
            slug: desiredSalesSlug,
          });
          nextPageId = response.page.id;
          createdSalesPageCount += 1;
          workingPages = [...workingPages, response.page];
        }

        setSubmitStatusLabel(`Creating ${item.pageName} (${index + 1}/${queuedItems.length})…`);
        const pageResponse = await post<{ page: FunnelPage }>(`/funnels/${funnelId}/pages`, {
          name: item.pageName,
          templateId: targetTemplateId,
          slug: item.slug || undefined,
          nextPageId,
        });
        const page = pageResponse.page;
        if (!firstGeneratedPageId) {
          firstGeneratedPageId = page.id;
        }
        workingPages = [...workingPages, page];

        setSubmitStatusLabel(`Generating ${item.pageName} (${index + 1}/${queuedItems.length})…`);
        await post(`/funnels/${funnelId}/pages/${page.id}/ai/generate`, {
          prompt: buildGenerationPrompt({
            productTitle: activeWorkspaceProduct.title,
            templateId: targetTemplateId,
            additionalInstructions,
          }),
          messages: [],
          referenceHtml: item.referenceHtml,
          referenceLabel: item.referenceLabel,
          referenceHtmlMode: "template",
          requireLatestStrategyCopy: true,
          generateImages,
        });
        completedImports += 1;
      }

      if (firstGeneratedPageId && (resolvedFunnel || !entryPageIdBeforeImport)) {
        setSubmitStatusLabel("Setting funnel entry page…");
        await request<Funnel>(`/funnels/${funnelId}`, {
          method: "PATCH",
          body: JSON.stringify({ entryPageId: firstGeneratedPageId }),
        });
      }

      await queryClient.invalidateQueries({ queryKey: ["funnels"] });

      if (targetTemplateId === "pre-sales-listicle" && salesWiringMode === "shared") {
        if (sharedSalesTarget === "existing" && sharedExistingSalesPageName) {
          toast.success(
            `Generated ${formatCount(queuedItems.length, "pre-sales page")} wired to "${sharedExistingSalesPageName}".`,
          );
        } else {
          const sharedName = createdSharedSalesPageName || sharedSalesPageName.trim() || defaultSharedSalesPageName();
          toast.success(
            `Generated ${formatCount(queuedItems.length, "pre-sales page")} and 1 shared sales page ("${sharedName}").`,
          );
        }
      } else if (targetTemplateId === "pre-sales-listicle" && salesWiringMode === "paired") {
        toast.success(
          `Generated ${formatCount(queuedItems.length, "pre-sales page")} and ${formatCount(createdSalesPageCount, "paired sales page")}.`,
        );
      } else {
        toast.success(`Generated ${formatCount(queuedItems.length, targetTemplateLabel(targetTemplateId).toLowerCase())}.`);
      }

      resetDraftComposer();
      setImportItems([]);
      navigate(`/research/funnels/${funnelId}`);
    } catch (error) {
      if (touchedFunnelId) {
        await queryClient.invalidateQueries({ queryKey: ["funnels"] });
      }
      const message = getApiErrorMessage(error, "Failed to generate funnel pages from imported HTML.");
      if (completedImports > 0) {
        toast.error(
          `Batch import stopped after ${completedImports} of ${queuedItems.length} imported page${completedImports === 1 ? "" : "s"}. ${message}`,
        );
      } else {
        toast.error(message);
      }
    } finally {
      setIsSubmitting(false);
      setSubmitStatusLabel(null);
    }
  };

  const generateButtonLabel = isBusy
    ? submitStatusLabel || `Generating ${targetTemplateLabel(targetTemplateId).toLowerCase()}…`
    : canReuseExistingTargetPage
      ? `Regenerate ${targetTemplateLabel(targetTemplateId).toLowerCase()}`
      : importCount > 1
        ? `Generate ${formatCount(importCount, targetTemplateLabel(targetTemplateId).toLowerCase())}`
        : `Generate ${targetTemplateLabel(targetTemplateId).toLowerCase()}`;

  return (
    <div className="ds-card ds-card--md space-y-4">
      <div>
        <div className="text-sm font-semibold text-content">Site imports</div>
        <div className="text-xs text-content-muted">
          Queue one or many HTML templates here, generate matching sales or pre-sales pages, and optionally wire every
          pre-sales page into one shared sales page or its own paired sales page.
        </div>
      </div>

      {!activeWorkspaceProduct ? (
        <div className="rounded-md border border-border bg-surface-2 p-3 text-xs text-content-muted">
          Select an active product to import HTML and generate funnel pages from this Sites workflow.
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label className="text-xs font-medium text-content">Target page type</label>
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
            placeholder={
              activeWorkspaceProduct ? defaultImportedFunnelName(activeWorkspaceProduct.title) : "Imported Template Funnel"
            }
            disabled={!activeWorkspaceProduct || isBusy}
          />
        </div>
      ) : null}

      <div className="space-y-2 rounded-md border border-divider bg-surface-2 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs font-semibold text-content">Imported HTML queue</div>
            <div className="text-[11px] text-content-muted">
              Upload multiple HTML files at once, or paste HTML and add it to the queue when you want a new page draft
              created from it.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => htmlFileInputRef.current?.click()}
              disabled={!activeWorkspaceProduct || isBusy}
            >
              Upload HTML files
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={handleAddDraftImport}
              disabled={!activeWorkspaceProduct || isBusy || !trimmedDraftReferenceHtml}
            >
              Add pasted HTML
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setImportItems([])}
              disabled={!importItems.length || isBusy}
            >
              Clear queue
            </Button>
          </div>
        </div>

        <input
          ref={htmlFileInputRef}
          className="hidden"
          type="file"
          accept="text/html,.html,.htm,text/plain"
          multiple
          onChange={handleReferenceHtmlSelect}
        />

        <div className="space-y-1">
          <label className="text-xs font-medium text-content">Paste another HTML template</label>
          <textarea
            rows={6}
            value={draftReferenceHtml}
            onChange={(event) => {
              setDraftReferenceHtml(event.target.value);
              setDraftReferenceLabel(null);
            }}
            placeholder="Paste full HTML here, then add it to the queue."
            disabled={!activeWorkspaceProduct || isBusy}
            className={cn(
              "min-h-[150px] w-full resize-y rounded-md border border-border bg-surface px-3 py-2 font-mono text-xs text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface placeholder:text-content-muted disabled:cursor-not-allowed disabled:opacity-60",
            )}
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-content-muted">
            <span>Draft source: {trimmedDraftReferenceHtml ? draftReferenceLabel || "pasted html" : "none"}</span>
            <span>
              {draftReferenceHtml.length.toLocaleString()} / {SITE_IMPORT_HTML_MAX_CHARS.toLocaleString()} characters
            </span>
          </div>
          {hasDraftConflict ? (
            <div className="text-[11px] text-warning">
              The pasted HTML is not in the queue yet. Add it or clear it before generating.
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-content">Queued pages</div>
            <div className="text-[11px] text-content-muted">
              {formatCount(importItems.length, targetTemplateLabel(targetTemplateId).toLowerCase())} queued
            </div>
          </div>

          {importItems.length ? (
            <div className="space-y-2">
              {importItems.map((item, index) => (
                <div key={item.id} className="rounded-md border border-border bg-surface p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-semibold text-content">
                        {index + 1}. {item.referenceLabel}
                      </div>
                      <div className="text-[11px] text-content-muted">
                        {item.referenceHtml.length.toLocaleString()} characters
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        setImportItems((current) => current.filter((currentItem) => currentItem.id !== item.id))
                      }
                      disabled={isBusy}
                    >
                      Remove
                    </Button>
                  </div>

                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-content">Page name</label>
                      <Input
                        value={item.pageName}
                        onChange={(event) =>
                          setImportItems((current) =>
                            current.map((currentItem) =>
                              currentItem.id === item.id ? { ...currentItem, pageName: event.target.value } : currentItem,
                            ),
                          )
                        }
                        disabled={isBusy}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-content">Slug</label>
                      <Input
                        value={item.slug}
                        onChange={(event) =>
                          setImportItems((current) =>
                            current.map((currentItem) =>
                              currentItem.id === item.id ? { ...currentItem, slug: event.target.value } : currentItem,
                            ),
                          )
                        }
                        placeholder="Leave blank to auto-generate from the page name."
                        disabled={isBusy}
                      />
                    </div>
                  </div>
                </div>
              ))}
              <div className="text-[11px] text-content-muted">
                Final slugs may still auto-adjust if the selected funnel already uses one.
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-border bg-surface p-3 text-xs text-content-muted">
              No HTML files queued yet. Upload one or more files, or paste HTML above and add it to the queue.
            </div>
          )}
        </div>
      </div>

      {targetTemplateId === "pre-sales-listicle" ? (
        <div className="space-y-3 rounded-md border border-border bg-surface-2 p-3">
          <div>
            <div className="text-xs font-semibold text-content">Sales page wiring</div>
            <div className="text-[11px] text-content-muted">
              Decide whether every generated pre-sales page should point nowhere, one shared sales page, or its own new
              paired sales page.
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-content">Wiring mode</label>
            <Select
              value={salesWiringMode}
              onValueChange={(value) => setSalesWiringMode(value as SiteImportSalesWiringMode)}
              options={[
                { label: "No sales page", value: "none" },
                { label: "One shared sales page", value: "shared" },
                { label: "One paired sales page per import", value: "paired" },
              ]}
              disabled={!activeWorkspaceProduct || isBusy}
            />
          </div>

          {salesWiringMode === "shared" ? (
            <div className="space-y-3">
              {selectedFunnelId !== NEW_FUNNEL_OPTION && salesPages.length ? (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-content">Shared sales page source</label>
                  <Select
                    value={sharedSalesTarget}
                    onValueChange={(value) => setSharedSalesTarget(value as SiteImportSharedSalesTarget)}
                    options={[
                      { label: "Use existing sales page", value: "existing" },
                      { label: "Create new shared sales page", value: "new" },
                    ]}
                    disabled={!activeWorkspaceProduct || isBusy}
                  />
                </div>
              ) : (
                <div className="rounded-md border border-border bg-surface p-3 text-[11px] text-content-muted">
                  A new shared sales page will be created for this batch because the selected funnel does not currently
                  expose an existing sales page to reuse.
                </div>
              )}

              {sharedSalesTarget === "existing" && selectedFunnelId !== NEW_FUNNEL_OPTION && salesPages.length ? (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-content">Shared sales page</label>
                  <Select
                    value={sharedSalesPageId}
                    onValueChange={setSharedSalesPageId}
                    options={salesPageOptions}
                    disabled={!activeWorkspaceProduct || isBusy}
                  />
                </div>
              ) : (
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-content">Shared sales page name</label>
                    <Input
                      value={sharedSalesPageName}
                      onChange={(event) => setSharedSalesPageName(event.target.value)}
                      placeholder="Sales Page"
                      disabled={!activeWorkspaceProduct || isBusy}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-content">Shared sales page slug</label>
                    <Input
                      value={sharedSalesPageSlug}
                      onChange={(event) => setSharedSalesPageSlug(event.target.value)}
                      placeholder="sales"
                      disabled={!activeWorkspaceProduct || isBusy}
                    />
                  </div>
                </div>
              )}
            </div>
          ) : null}

          {salesWiringMode === "paired" ? (
            <div className="rounded-md border border-border bg-surface p-3 text-[11px] text-content-muted">
              Each pre-sales import will create a fresh sales page using the same base name and a matching slug such as
              <span className="font-mono"> story-a-sales</span>.
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-1">
        <label className="text-xs font-medium text-content">Additional instructions</label>
        <textarea
          rows={4}
          value={additionalInstructions}
          onChange={(event) => setAdditionalInstructions(event.target.value)}
          placeholder="Optional: describe how you want these pages adapted."
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
            Latest strategy copy is required and will be injected into the imported HTML without rebuilding the
            template structure.
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
        disabled={
          !activeWorkspaceProduct ||
          !importCount ||
          isBusy ||
          (selectedFunnelId !== NEW_FUNNEL_OPTION && isLoadingSelectedFunnel)
        }
      >
        {generateButtonLabel}
      </Button>
    </div>
  );
}
