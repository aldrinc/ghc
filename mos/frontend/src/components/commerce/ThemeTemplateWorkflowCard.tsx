import { useEffect, useMemo, useRef, useState } from "react";
import {
  useBuildClientShopifyThemeTemplateDraft,
  useDownloadClientShopifyThemeTemplateZip,
  useGenerateClientShopifyThemeTemplateImages,
  useListClientShopifyThemeTemplateDrafts,
  useUpdateClientShopifyThemeTemplateDraft,
} from "@/api/clients";
import { useAssets } from "@/api/assets";
import { useUploadProductAssets } from "@/api/products";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { resolveOptionalApiBaseUrl } from "@/lib/apiBaseUrl";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import {
  DEFAULT_SHOPIFY_THEME_NAME,
  parseStringMap,
  buildImageSlotPathOrder,
  orderStringMapByPreferredPaths,
  areStringMapsEqual,
  parseSlotPathList,
  collectTemplateGenerationNonFatalErrors,
  humanizeSlotToken,
  buildImageSlotReadableLabelMap,
  buildTextSlotReadableLabelMap,
} from "@/lib/shopifyTemplateUtils";

type ThemeTemplateWorkflowCardProps = {
  workspaceId: string;
  shopifySyncShopDomain: string;
  designSystemOptions: Array<{ label: string; value: string }>;
  isLoadingDesignSystems: boolean;
  workspaceProducts: Array<{ id: string; title: string }>;
  activeWorkspaceProduct: { id: string; title: string } | null;
};

export function ThemeTemplateWorkflowCard({
  workspaceId,
  shopifySyncShopDomain,
  designSystemOptions,
  isLoadingDesignSystems,
  workspaceProducts,
  activeWorkspaceProduct,
}: ThemeTemplateWorkflowCardProps) {
  // --- API hooks ---
  const buildShopifyThemeTemplateDraft = useBuildClientShopifyThemeTemplateDraft(workspaceId);
  const generateShopifyThemeTemplateImages = useGenerateClientShopifyThemeTemplateImages(workspaceId);
  const downloadShopifyThemeTemplateZip = useDownloadClientShopifyThemeTemplateZip(workspaceId);
  const updateShopifyThemeTemplateDraft = useUpdateClientShopifyThemeTemplateDraft(workspaceId);
  const {
    data: shopifyThemeTemplateDrafts = [],
    isFetched: hasFetchedShopifyThemeTemplateDrafts,
    isLoading: isLoadingShopifyThemeTemplateDrafts,
    refetch: refetchShopifyThemeTemplateDrafts,
  } = useListClientShopifyThemeTemplateDrafts(workspaceId);
  const {
    data: workspaceImageAssets = [],
    isLoading: isLoadingWorkspaceImageAssets,
    refetch: refetchWorkspaceImageAssets,
  } = useAssets({ clientId: workspaceId, assetKind: "image" }, { enabled: Boolean(workspaceId) });

  // --- State ---
  const [themeSyncDesignSystemId, setThemeSyncDesignSystemId] = useState("");
  const [themeSyncThemeName, setThemeSyncThemeName] = useState(DEFAULT_SHOPIFY_THEME_NAME);
  const [themeSyncProductId, setThemeSyncProductId] = useState("");
  const [selectedTemplateDraftId, setSelectedTemplateDraftId] = useState("");
  const [templateImageGenerationSlotPathsInput, setTemplateImageGenerationSlotPathsInput] = useState("");
  const [templateDraftImageMapInput, setTemplateDraftImageMapInput] = useState("{}");
  const [templateDraftTextValuesInput, setTemplateDraftTextValuesInput] = useState("{}");
  const [templateDraftEditError, setTemplateDraftEditError] = useState<string | null>(null);
  const [templateAssetUploadProductId, setTemplateAssetUploadProductId] = useState("");
  const [templateAssetSearchQuery, setTemplateAssetSearchQuery] = useState("");
  const [templateSlotAssetQueryByPath, setTemplateSlotAssetQueryByPath] = useState<Record<string, string>>({});
  const [templateAssetPickerImageErrorsByPublicId, setTemplateAssetPickerImageErrorsByPublicId] = useState<Record<string, boolean>>({});
  const [clearingTemplateDraftImageSlotPath, setClearingTemplateDraftImageSlotPath] = useState("");
  const [templatePreviewDialogOpen, setTemplatePreviewDialogOpen] = useState(false);
  const [templatePreviewImageMap, setTemplatePreviewImageMap] = useState<Record<string, string>>({});
  const [templatePreviewTextValues, setTemplatePreviewTextValues] = useState<Record<string, string>>({});
  const [templatePreviewImageErrorsByPath, setTemplatePreviewImageErrorsByPath] = useState<Record<string, boolean>>({});
  const [mappedImageSlotsDialogOpen, setMappedImageSlotsDialogOpen] = useState(false);

  // --- Refs ---
  const templateAssetUploadInputRef = useRef<HTMLInputElement | null>(null);
  const autoCreateBaseTemplateDraftAttemptKeyRef = useRef("");
  const templateDraftPersistQueueRef = useRef<Promise<void>>(Promise.resolve());

  // --- Upload hook ---
  const uploadTemplateProductAssets = useUploadProductAssets(templateAssetUploadProductId || "");

  // --- Computed values / memos ---
  const templateDraftOptions = useMemo(
    () =>
      shopifyThemeTemplateDrafts.map((draft) => ({
        label: `${draft.themeName} · v${draft.latestVersion?.versionNumber ?? 0}`,
        value: draft.id,
      })),
    [shopifyThemeTemplateDrafts]
  );

  const selectedTemplateDraftStorageKey = useMemo(() => {
    if (!workspaceId) return "";
    return `workspace:${workspaceId}:shopify:template-draft-id`;
  }, [workspaceId]);

  const selectedTemplateDraft = useMemo(
    () => shopifyThemeTemplateDrafts.find((draft) => draft.id === selectedTemplateDraftId) ?? null,
    [shopifyThemeTemplateDrafts, selectedTemplateDraftId]
  );

  const apiBaseUrl = resolveOptionalApiBaseUrl();
  const publicAssetBaseUrl = apiBaseUrl?.replace(/\/$/, "");

  const productById = useMemo(
    () => new Map(workspaceProducts.map((product) => [product.id, product])),
    [workspaceProducts]
  );

  const templateAssetUploadProductOptions = useMemo(
    () =>
      workspaceProducts.map((product) => ({
        label: product.title,
        value: product.id,
      })),
    [workspaceProducts]
  );

  const workspaceProductImageAssets = useMemo(
    () =>
      workspaceImageAssets
        .filter((asset) => asset.product_id)
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [workspaceImageAssets]
  );

  const workspaceProductImageAssetEntries = useMemo(
    () =>
      workspaceProductImageAssets.map((asset) => {
        const productTitle = asset.product_id ? productById.get(asset.product_id)?.title : undefined;
        const createdAt = new Date(asset.created_at);
        const createdAtLabel = Number.isNaN(createdAt.getTime())
          ? asset.created_at
          : createdAt.toLocaleDateString();
        const dimensions =
          typeof asset.width === "number" && typeof asset.height === "number"
            ? `${asset.width}x${asset.height}`
            : "size unknown";
        const tagsLabel = asset.tags?.length ? asset.tags.join(", ") : "";
        const optionLabel = `${productTitle || "Unknown product"} · ${asset.public_id.slice(0, 8)} · ${dimensions} · ${createdAtLabel}`;
        const searchText = [
          productTitle || "",
          asset.product_id || "",
          asset.public_id,
          dimensions,
          asset.status,
          asset.file_status || "",
          asset.format,
          tagsLabel,
        ]
          .join(" ")
          .toLowerCase();
        return {
          asset,
          productTitle: productTitle || "Unknown product",
          createdAtLabel,
          dimensions,
          tagsLabel,
          optionLabel,
          searchText,
        };
      }),
    [productById, workspaceProductImageAssets]
  );

  const normalizedTemplateAssetSearchQuery = templateAssetSearchQuery.trim().toLowerCase();

  const filteredWorkspaceProductImageAssetEntries = useMemo(() => {
    if (!normalizedTemplateAssetSearchQuery) return workspaceProductImageAssetEntries;
    return workspaceProductImageAssetEntries.filter((entry) =>
      entry.searchText.includes(normalizedTemplateAssetSearchQuery)
    );
  }, [workspaceProductImageAssetEntries, normalizedTemplateAssetSearchQuery]);

  const workspaceProductImageAssetByPublicId = useMemo(
    () => new Map(workspaceProductImageAssetEntries.map((entry) => [entry.asset.public_id, entry])),
    [workspaceProductImageAssetEntries]
  );

  const parsedTemplateDraftImageMapResult = useMemo(
    () => parseStringMap(templateDraftImageMapInput, "Image map"),
    [templateDraftImageMapInput]
  );
  const parsedTemplateDraftImageMap = parsedTemplateDraftImageMapResult.value || {};

  const parsedTemplateDraftTextValuesResult = useMemo(
    () => parseStringMap(templateDraftTextValuesInput, "Text values"),
    [templateDraftTextValuesInput]
  );
  const parsedTemplateDraftTextValues = parsedTemplateDraftTextValuesResult.value || {};

  const templateImageSlotReadableLabelByPath = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return new Map<string, string>();
    return buildImageSlotReadableLabelMap(latestVersion.data.imageSlots);
  }, [selectedTemplateDraft?.latestVersion?.id]);

  const templateImageSlotPathOrder = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return [] as string[];
    return buildImageSlotPathOrder(latestVersion.data.imageSlots);
  }, [selectedTemplateDraft?.latestVersion?.id]);

  const templateTextSlotReadableLabelByPath = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return new Map<string, string>();
    return buildTextSlotReadableLabelMap(latestVersion.data.textSlots);
  }, [selectedTemplateDraft?.latestVersion?.id]);

  const mappedTemplateImageSlotEntries = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    const slotByPath = new Map((latestVersion?.data.imageSlots || []).map((slot) => [slot.path, slot]));
    const orderedImageMap = orderStringMapByPreferredPaths(
      parsedTemplateDraftImageMap,
      templateImageSlotPathOrder
    );
    return Object.entries(orderedImageMap)
      .filter(([path, assetPublicId]) => path.trim() && typeof assetPublicId === "string" && assetPublicId.trim())
      .map(([path, assetPublicId]) => {
        const slot = slotByPath.get(path);
        const readableSlotLabel =
          templateImageSlotReadableLabelByPath.get(path) ||
          humanizeSlotToken(path.split(".").pop() || path);
        return {
          path,
          assetPublicId: assetPublicId.trim(),
          readableSlotLabel,
          role: slot?.role || "",
          recommendedAspect: slot?.recommendedAspect || "",
        };
      });
  }, [
    parsedTemplateDraftImageMap,
    selectedTemplateDraft?.latestVersion?.id,
    templateImageSlotPathOrder,
    templateImageSlotReadableLabelByPath,
  ]);

  const templatePreviewImageItems = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return [];

    const slotByPath = new Map(
      latestVersion.data.imageSlots.map((slot) => [slot.path, slot])
    );
    const seenPaths = new Set<string>();
    const items: Array<{
      path: string;
      assetPublicId: string;
      role?: string;
      recommendedAspect?: string;
      hasKnownSlot: boolean;
    }> = [];

    for (const slot of latestVersion.data.imageSlots) {
      const path = slot.path;
      seenPaths.add(path);
      items.push({
        path,
        assetPublicId: templatePreviewImageMap[path] || "",
        role: slot.role,
        recommendedAspect: slot.recommendedAspect,
        hasKnownSlot: true,
      });
    }

    for (const [path, assetPublicId] of Object.entries(templatePreviewImageMap)) {
      if (seenPaths.has(path)) continue;
      const slot = slotByPath.get(path);
      items.push({
        path,
        assetPublicId,
        role: slot?.role,
        recommendedAspect: slot?.recommendedAspect,
        hasKnownSlot: false,
      });
    }

    return items;
  }, [selectedTemplateDraft?.latestVersion, templatePreviewImageMap]);

  const templatePreviewTextEntries = useMemo(
    () => Object.entries(templatePreviewTextValues).sort(([a], [b]) => a.localeCompare(b)),
    [templatePreviewTextValues]
  );

  // --- Effects ---
  useEffect(() => {
    if (!shopifyThemeTemplateDrafts.length) {
      setSelectedTemplateDraftId("");
      return;
    }
    setSelectedTemplateDraftId((current) => {
      const normalizedCurrent = current.trim();
      if (
        normalizedCurrent &&
        shopifyThemeTemplateDrafts.some((draft) => draft.id === normalizedCurrent)
      ) {
        return normalizedCurrent;
      }
      if (typeof window !== "undefined" && selectedTemplateDraftStorageKey) {
        const storedDraftId = window.localStorage.getItem(selectedTemplateDraftStorageKey) || "";
        const normalizedStoredDraftId = storedDraftId.trim();
        if (
          normalizedStoredDraftId &&
          shopifyThemeTemplateDrafts.some((draft) => draft.id === normalizedStoredDraftId)
        ) {
          return normalizedStoredDraftId;
        }
      }
      return shopifyThemeTemplateDrafts[0]?.id || "";
    });
  }, [shopifyThemeTemplateDrafts, selectedTemplateDraftStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined" || !selectedTemplateDraftStorageKey) return;
    const normalizedDraftId = selectedTemplateDraftId.trim();
    if (!normalizedDraftId) {
      window.localStorage.removeItem(selectedTemplateDraftStorageKey);
      return;
    }
    window.localStorage.setItem(selectedTemplateDraftStorageKey, normalizedDraftId);
  }, [selectedTemplateDraftId, selectedTemplateDraftStorageKey]);

  useEffect(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) {
      setTemplateDraftImageMapInput("{}");
      setTemplateDraftTextValuesInput("{}");
      setTemplateDraftEditError(null);
      return;
    }
    const imageSlotPathOrder = buildImageSlotPathOrder(latestVersion.data.imageSlots);
    const orderedImageMap = orderStringMapByPreferredPaths(
      latestVersion.data.componentImageAssetMap || {},
      imageSlotPathOrder
    );
    setTemplateDraftImageMapInput(
      JSON.stringify(orderedImageMap, null, 2)
    );
    setTemplateDraftTextValuesInput(
      JSON.stringify(latestVersion.data.componentTextValues || {}, null, 2)
    );
    setTemplateImageGenerationSlotPathsInput("");
    setTemplateDraftEditError(null);
    setTemplateAssetSearchQuery("");
    setTemplateSlotAssetQueryByPath({});
    setTemplateAssetPickerImageErrorsByPublicId({});
    setClearingTemplateDraftImageSlotPath("");
  }, [selectedTemplateDraft?.id, selectedTemplateDraft?.latestVersion?.id]);

  useEffect(() => {
    if (!workspaceProducts.length) {
      setTemplateAssetUploadProductId("");
      return;
    }
    setTemplateAssetUploadProductId((current) => {
      const draftProductId =
        selectedTemplateDraft?.latestVersion?.data.productId?.trim() ||
        selectedTemplateDraft?.productId?.trim() ||
        themeSyncProductId.trim();
      if (draftProductId && workspaceProducts.some((product) => product.id === draftProductId)) {
        return draftProductId;
      }
      if (current && workspaceProducts.some((product) => product.id === current)) return current;
      const activeWorkspaceProductId = activeWorkspaceProduct?.id?.trim() || "";
      if (
        activeWorkspaceProductId &&
        workspaceProducts.some((product) => product.id === activeWorkspaceProductId)
      ) {
        return activeWorkspaceProductId;
      }
      return workspaceProducts[0]?.id || "";
    });
  }, [
    activeWorkspaceProduct?.id,
    workspaceProducts,
    selectedTemplateDraft?.id,
    selectedTemplateDraft?.productId,
    selectedTemplateDraft?.latestVersion?.data.productId,
    themeSyncProductId,
  ]);

  useEffect(() => {
    if (shopifyThemeTemplateDrafts.length) {
      autoCreateBaseTemplateDraftAttemptKeyRef.current = "";
    }
  }, [shopifyThemeTemplateDrafts.length]);

  useEffect(() => {
    if (!workspaceId) return;
    if (!hasFetchedShopifyThemeTemplateDrafts || isLoadingShopifyThemeTemplateDrafts) return;
    if (shopifyThemeTemplateDrafts.length) return;
    if (buildShopifyThemeTemplateDraft.isPending) return;
    const nextThemeName = themeSyncThemeName.trim();

    const attemptKey = [
      workspaceId,
      shopifySyncShopDomain.trim().toLowerCase(),
      themeSyncDesignSystemId.trim(),
      themeSyncProductId.trim(),
      nextThemeName,
    ].join("|");
    if (autoCreateBaseTemplateDraftAttemptKeyRef.current === attemptKey) return;
    autoCreateBaseTemplateDraftAttemptKeyRef.current = attemptKey;
    void handleCreateBaseTemplateDraft();
  }, [
    workspaceId,
    hasFetchedShopifyThemeTemplateDrafts,
    isLoadingShopifyThemeTemplateDrafts,
    shopifyThemeTemplateDrafts.length,
    buildShopifyThemeTemplateDraft.isPending,
    shopifySyncShopDomain,
    themeSyncDesignSystemId,
    themeSyncProductId,
    themeSyncThemeName,
  ]);

  // --- Handlers ---
  const persistTemplateDraftEdits = async ({
    componentImageAssetMap,
    componentTextValues,
  }: {
    componentImageAssetMap: Record<string, string>;
    componentTextValues: Record<string, string>;
  }) => {
    if (!workspaceId || !selectedTemplateDraftId) return;
    const orderedImageMap = orderStringMapByPreferredPaths(
      componentImageAssetMap,
      templateImageSlotPathOrder
    );
    const persistPromise = templateDraftPersistQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        await updateShopifyThemeTemplateDraft.mutateAsync({
          draftId: selectedTemplateDraftId,
          payload: {
            componentImageAssetMap: orderedImageMap,
            componentTextValues,
          },
          suppressSuccessToast: true,
        });
        setTemplateDraftEditError(null);
      });
    templateDraftPersistQueueRef.current = persistPromise;
    await persistPromise;
  };

  const handleCreateBaseTemplateDraft = async () => {
    if (!workspaceId) return;
    const nextThemeName = themeSyncThemeName.trim();

    const payload: {
      themeName?: string;
      shopDomain?: string;
      designSystemId?: string;
      productId?: string;
    } = {};
    if (nextThemeName) payload.themeName = nextThemeName;

    const normalizedShopDomain = shopifySyncShopDomain.trim().toLowerCase();
    if (normalizedShopDomain) payload.shopDomain = normalizedShopDomain;
    const normalizedDesignSystemId = themeSyncDesignSystemId.trim();
    if (normalizedDesignSystemId) payload.designSystemId = normalizedDesignSystemId;
    const normalizedProductId =
      themeSyncProductId.trim() ||
      activeWorkspaceProduct?.id?.trim() ||
      templateAssetUploadProductId.trim();
    if (normalizedProductId) payload.productId = normalizedProductId;

    try {
      const response = await buildShopifyThemeTemplateDraft.mutateAsync(payload);
      const draftId = response.draft.id;
      const draftProductId = response.draft.productId?.trim() || normalizedProductId;
      setSelectedTemplateDraftId(draftId);
      setTemplateDraftEditError(null);
      await refetchShopifyThemeTemplateDrafts();
      if (!draftProductId) {
        const errorMessage =
          "Template draft created, but product-specific copy generation requires a productId.";
        setTemplateDraftEditError(errorMessage);
        toast.error(errorMessage);
        return;
      }
      const generationResponse = await generateShopifyThemeTemplateImages.mutateAsync({
        draftId,
        productId: draftProductId,
      });
      const nonFatalErrors = collectTemplateGenerationNonFatalErrors(generationResponse);
      await refetchShopifyThemeTemplateDrafts();
      setTemplateDraftEditError(nonFatalErrors.length ? nonFatalErrors.join(" ") : null);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleGenerateTemplateDraftImages = async () => {
    if (!workspaceId) return;
    if (!selectedTemplateDraftId) {
      toast.error("Select a template draft first.");
      return;
    }
    const parsedSlotPathList = parseSlotPathList(templateImageGenerationSlotPathsInput);
    if (!parsedSlotPathList.value) {
      setTemplateDraftEditError(parsedSlotPathList.error || "Invalid image generation slot paths.");
      return;
    }
    const payload: {
      draftId: string;
      productId?: string;
      slotPaths?: string[];
    } = {
      draftId: selectedTemplateDraftId,
    };
    const explicitProductId =
      selectedTemplateDraft?.latestVersion?.data.productId?.trim() ||
      selectedTemplateDraft?.productId?.trim() ||
      templateAssetUploadProductId.trim() ||
      themeSyncProductId.trim();
    if (explicitProductId) payload.productId = explicitProductId;
    if (parsedSlotPathList.value.length) payload.slotPaths = parsedSlotPathList.value;
    setTemplateDraftEditError(null);

    const response = await generateShopifyThemeTemplateImages.mutateAsync(payload);
    const draftsResponse = await refetchShopifyThemeTemplateDrafts();
    const refreshedDrafts = draftsResponse.data || [];
    const refreshedDraft = refreshedDrafts.find((draft) => draft.id === response.draft.id);
    if (!refreshedDraft?.latestVersion) {
      const errorMessage =
        "Generated images were not persisted to the template draft. Refresh and retry generation.";
      setTemplateDraftEditError(errorMessage);
      toast.error(errorMessage);
      return;
    }
    setSelectedTemplateDraftId(refreshedDraft.id);
    const refreshedImageSlotPathOrder = buildImageSlotPathOrder(
      refreshedDraft.latestVersion.data.imageSlots
    );
    const refreshedOrderedImageMap = orderStringMapByPreferredPaths(
      refreshedDraft.latestVersion.data.componentImageAssetMap || {},
      refreshedImageSlotPathOrder
    );
    setTemplateDraftImageMapInput(
      JSON.stringify(refreshedOrderedImageMap, null, 2)
    );
    setTemplateDraftTextValuesInput(
      JSON.stringify(refreshedDraft.latestVersion.data.componentTextValues || {}, null, 2)
    );
    const generatedProductId = refreshedDraft.latestVersion.data.productId?.trim();
    if (generatedProductId) {
      setTemplateAssetUploadProductId(generatedProductId);
    }
    const nonFatalErrors = collectTemplateGenerationNonFatalErrors(response);
    setTemplateDraftEditError(nonFatalErrors.length ? nonFatalErrors.join(" ") : null);
    await refetchWorkspaceImageAssets();
  };

  const handleClearTemplateDraftImageMappings = async () => {
    if (!workspaceId) return;
    if (!selectedTemplateDraftId) {
      toast.error("Select a template draft first.");
      return;
    }
    try {
      await updateShopifyThemeTemplateDraft.mutateAsync({
        draftId: selectedTemplateDraftId,
        payload: {
          componentImageAssetMap: {},
          notes: "Cleared mapped image slots.",
        },
      });
      setTemplateDraftImageMapInput("{}");
      setTemplateSlotAssetQueryByPath({});
      setTemplateAssetPickerImageErrorsByPublicId({});
      setClearingTemplateDraftImageSlotPath("");
      setTemplateDraftEditError(null);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleClearTemplateDraftImageMapping = async (slotPath: string) => {
    if (!workspaceId) return;
    if (!selectedTemplateDraftId) {
      toast.error("Select a template draft first.");
      return;
    }
    const parsedImageMap = parseStringMap(templateDraftImageMapInput, "Image map");
    if (!parsedImageMap.value) {
      setTemplateDraftEditError(parsedImageMap.error || "Invalid image map.");
      return;
    }
    const normalizedSlotPath = slotPath.trim();
    if (!normalizedSlotPath) return;
    if (!Object.prototype.hasOwnProperty.call(parsedImageMap.value, normalizedSlotPath)) {
      return;
    }
    const nextImageMap = { ...parsedImageMap.value };
    delete nextImageMap[normalizedSlotPath];
    const orderedNextImageMap = orderStringMapByPreferredPaths(
      nextImageMap,
      templateImageSlotPathOrder
    );
    setClearingTemplateDraftImageSlotPath(normalizedSlotPath);
    try {
      await updateShopifyThemeTemplateDraft.mutateAsync({
        draftId: selectedTemplateDraftId,
        payload: {
          componentImageAssetMap: orderedNextImageMap,
          notes: `Cleared mapped image slot: ${normalizedSlotPath}`,
        },
      });
      setTemplateDraftImageMapInput(JSON.stringify(orderedNextImageMap, null, 2));
      setTemplateSlotAssetQueryByPath((current) => {
        if (!Object.prototype.hasOwnProperty.call(current, normalizedSlotPath)) return current;
        const next = { ...current };
        delete next[normalizedSlotPath];
        return next;
      });
      setTemplateDraftEditError(null);
    } catch {
      // Error toast is emitted by the mutation hook.
    } finally {
      setClearingTemplateDraftImageSlotPath("");
    }
  };

  const handleTemplateDraftSlotAssetChange = (path: string, assetPublicId: string) => {
    const parsedImageMap = parseStringMap(templateDraftImageMapInput, "Image map");
    if (!parsedImageMap.value) {
      setTemplateDraftEditError(parsedImageMap.error || "Invalid image map.");
      return;
    }
    const parsedTextValues = parseStringMap(templateDraftTextValuesInput, "Text values");
    if (!parsedTextValues.value) {
      setTemplateDraftEditError(parsedTextValues.error || "Invalid text values.");
      return;
    }
    const nextImageMap = { ...parsedImageMap.value };
    const cleanedAssetPublicId = assetPublicId.trim();
    if (cleanedAssetPublicId) {
      nextImageMap[path] = cleanedAssetPublicId;
    } else {
      delete nextImageMap[path];
    }
    const orderedNextImageMap = orderStringMapByPreferredPaths(
      nextImageMap,
      templateImageSlotPathOrder
    );
    setTemplateDraftImageMapInput(JSON.stringify(orderedNextImageMap, null, 2));
    setTemplateDraftEditError(null);
    void persistTemplateDraftEdits({
      componentImageAssetMap: orderedNextImageMap,
      componentTextValues: parsedTextValues.value,
    }).catch(() => {
      // Error toast is emitted by the mutation hook.
    });
  };

  const handleTemplateDraftSlotTextValueChange = (path: string, nextValue: string) => {
    const parsedImageMap = parseStringMap(templateDraftImageMapInput, "Image map");
    if (!parsedImageMap.value) {
      setTemplateDraftEditError(parsedImageMap.error || "Invalid image map.");
      return;
    }
    const parsedTextValues = parseStringMap(templateDraftTextValuesInput, "Text values");
    if (!parsedTextValues.value) {
      setTemplateDraftEditError(parsedTextValues.error || "Invalid text values.");
      return;
    }
    const nextTextValues = { ...parsedTextValues.value };
    if (nextValue.trim()) {
      nextTextValues[path] = nextValue;
    } else {
      delete nextTextValues[path];
    }
    setTemplateDraftTextValuesInput(JSON.stringify(nextTextValues, null, 2));
    setTemplateDraftEditError(null);
    void persistTemplateDraftEdits({
      componentImageAssetMap: parsedImageMap.value,
      componentTextValues: nextTextValues,
    }).catch(() => {
      // Error toast is emitted by the mutation hook.
    });
  };

  const handleTemplateImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      toast.error("No files selected.");
      event.currentTarget.value = "";
      return;
    }
    if (!templateAssetUploadProductId.trim()) {
      toast.error("Select a product before uploading images.");
      event.currentTarget.value = "";
      return;
    }
    const nonImageFiles = files.filter((file) => !file.type.toLowerCase().startsWith("image/"));
    if (nonImageFiles.length) {
      toast.error("Only image files are allowed in this uploader.");
      event.currentTarget.value = "";
      return;
    }
    try {
      await uploadTemplateProductAssets.mutateAsync(files);
      await refetchWorkspaceImageAssets();
    } finally {
      event.currentTarget.value = "";
    }
  };

  const openTemplatePreview = () => {
    if (!selectedTemplateDraft?.latestVersion) {
      toast.error("Build or select a template draft first.");
      return;
    }
    const parsedImageMap = parseStringMap(templateDraftImageMapInput, "Image map");
    if (!parsedImageMap.value) {
      setTemplateDraftEditError(parsedImageMap.error || "Invalid image map.");
      return;
    }
    const parsedTextValues = parseStringMap(templateDraftTextValuesInput, "Text values");
    if (!parsedTextValues.value) {
      setTemplateDraftEditError(parsedTextValues.error || "Invalid text values.");
      return;
    }
    setTemplateDraftEditError(null);
    setTemplatePreviewImageMap(parsedImageMap.value);
    setTemplatePreviewTextValues(parsedTextValues.value);
    setTemplatePreviewImageErrorsByPath({});
    setTemplatePreviewDialogOpen(true);
  };

  const handleOpenTemplatePreview = () => {
    openTemplatePreview();
  };

  const handleOpenMappedImageSlotsModal = () => {
    if (!selectedTemplateDraft?.latestVersion) {
      toast.error("Build or select a template draft first.");
      return;
    }
    setMappedImageSlotsDialogOpen(true);
  };

  const handleDownloadTemplateZip = async () => {
    if (!workspaceId) return;
    if (!selectedTemplateDraftId.trim()) {
      toast.error("Select a template draft first.");
      return;
    }
    const parsedImageMap = parseStringMap(templateDraftImageMapInput, "Image map");
    if (!parsedImageMap.value) {
      const message = parsedImageMap.error || "Invalid image map.";
      setTemplateDraftEditError(message);
      toast.error(message);
      return;
    }
    const parsedTextValues = parseStringMap(templateDraftTextValuesInput, "Text values");
    if (!parsedTextValues.value) {
      const message = parsedTextValues.error || "Invalid text values.";
      setTemplateDraftEditError(message);
      toast.error(message);
      return;
    }
    const currentOrderedImageMap = orderStringMapByPreferredPaths(
      parsedImageMap.value,
      templateImageSlotPathOrder
    );
    const latestVersionData = selectedTemplateDraft?.latestVersion?.data;
    const latestOrderedImageMap = orderStringMapByPreferredPaths(
      latestVersionData?.componentImageAssetMap || {},
      templateImageSlotPathOrder
    );
    const latestTextValues = latestVersionData?.componentTextValues || {};
    const hasUnsavedDraftEdits =
      !areStringMapsEqual(currentOrderedImageMap, latestOrderedImageMap) ||
      !areStringMapsEqual(parsedTextValues.value, latestTextValues);
    try {
      if (hasUnsavedDraftEdits) {
        await persistTemplateDraftEdits({
          componentImageAssetMap: currentOrderedImageMap,
          componentTextValues: parsedTextValues.value,
        });
      } else {
        await templateDraftPersistQueueRef.current;
      }
      setTemplateDraftEditError(null);
    } catch {
      // Error toast is emitted by the mutation hook.
      return;
    }
    try {
      await downloadShopifyThemeTemplateZip.mutateAsync({
        draftId: selectedTemplateDraftId.trim(),
      });
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  // --- Render ---
  return (
    <>
      <div className="ds-card ds-card--md space-y-4">
        {/* Header */}
        <div>
          <div className="text-sm font-semibold text-content">Theme template</div>
          <div className="text-xs text-content-muted">
            Build a template draft, generate images and text, then export as a ZIP.
          </div>
        </div>

        {/* Config grid */}
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <label className="text-xs font-medium text-content">Theme name</label>
            <Input
              value={themeSyncThemeName}
              onChange={(event) => setThemeSyncThemeName(event.target.value)}
              placeholder={DEFAULT_SHOPIFY_THEME_NAME}
            />
            <div className="text-[11px] text-content-muted">
              Default: {DEFAULT_SHOPIFY_THEME_NAME}. Clear to use the store&apos;s main theme.
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-content">Product ID</label>
            <Input
              value={themeSyncProductId}
              onChange={(event) => setThemeSyncProductId(event.target.value)}
              placeholder="Optional"
            />
            <div className="text-[11px] text-content-muted">
              Scope image/text planning to a specific product.
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-content">Design system</label>
            <Select
              value={themeSyncDesignSystemId}
              onValueChange={(value) => setThemeSyncDesignSystemId(value)}
              options={
                designSystemOptions.length > 1
                  ? designSystemOptions
                  : [{ label: isLoadingDesignSystems ? "Loading\u2026" : "No design systems", value: "" }]
              }
              disabled={designSystemOptions.length <= 1}
            />
            <div className="text-[11px] text-content-muted">
              Workspace default unless overridden.
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-content">Template draft</label>
            <Select
              value={selectedTemplateDraftId}
              onValueChange={(value) => setSelectedTemplateDraftId(value)}
              options={
                templateDraftOptions.length
                  ? templateDraftOptions
                  : [{ label: "No drafts yet", value: "" }]
              }
              disabled={!templateDraftOptions.length}
            />
            <div className="text-[11px] text-content-muted">
              Select a draft to review or export.
            </div>
          </div>
        </div>

        {selectedTemplateDraft?.latestVersion ? (
          <div className="space-y-3">
            {/*
            <div className="space-y-3 rounded-md border border-divider p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold text-content">Image asset picker</div>
                  <div className="text-xs text-content-muted">
                    Search workspace product images, then map each template image slot.
                  </div>
                </div>
                <div className="w-full space-y-2 lg:w-auto lg:min-w-[520px]">
                  <Input
                    value={templateAssetSearchQuery}
                    onChange={(event) => setTemplateAssetSearchQuery(event.target.value)}
                    placeholder="Search by product, asset ID, size, status, tag"
                  />
                  <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                    <Select
                      value={templateAssetUploadProductId}
                      onValueChange={(value) => setTemplateAssetUploadProductId(value)}
                      options={
                        templateAssetUploadProductOptions.length
                          ? templateAssetUploadProductOptions
                          : [{ label: "No products in this workspace", value: "" }]
                      }
                      disabled={!templateAssetUploadProductOptions.length || uploadTemplateProductAssets.isPending}
                    />
                    <div className="flex items-center gap-2">
                      <input
                        ref={templateAssetUploadInputRef}
                        className="hidden"
                        type="file"
                        multiple
                        accept="image/*"
                        onChange={handleTemplateImageUpload}
                      />
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => templateAssetUploadInputRef.current?.click()}
                        disabled={!templateAssetUploadProductOptions.length || uploadTemplateProductAssets.isPending}
                      >
                        {uploadTemplateProductAssets.isPending ? "Uploading\u2026" : "Upload images"}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>

              {!publicAssetBaseUrl ? (
                <div className="rounded-md border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                  Missing `VITE_API_BASE_URL`; picker image previews cannot be loaded.
                </div>
              ) : null}

              {parsedTemplateDraftImageMapResult.error ? (
                <div className="rounded-md border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                  {parsedTemplateDraftImageMapResult.error}
                </div>
              ) : isLoadingWorkspaceImageAssets ? (
                <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                  Loading product image assets\u2026
                </div>
              ) : !workspaceProductImageAssetEntries.length ? (
                <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                  No product image assets were found for this workspace.
                </div>
              ) : !selectedTemplateDraft.latestVersion.data.imageSlots.length ? (
                <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                  This draft has no image slots to map.
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-xs text-content-muted">
                    Showing{" "}
                    <span className="font-semibold text-content">{filteredWorkspaceProductImageAssetEntries.length}</span> of{" "}
                    <span className="font-semibold text-content">{workspaceProductImageAssetEntries.length}</span> product image assets.
                  </div>
                  <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                    <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                      {selectedTemplateDraft.latestVersion.data.imageSlots.map((slot) => {
                        const selectedAssetPublicId = parsedTemplateDraftImageMap[slot.path] || "";
                        const selectedAssetEntry =
                          selectedAssetPublicId
                            ? workspaceProductImageAssetByPublicId.get(selectedAssetPublicId)
                            : undefined;
                        const readableSlotLabel =
                          templateImageSlotReadableLabelByPath.get(slot.path) ||
                          humanizeSlotToken(slot.path.split(".").pop() || slot.path);
                        const slotAssetQuery = templateSlotAssetQueryByPath[slot.path] ?? selectedAssetPublicId;
                        const normalizedSlotAssetQuery = slotAssetQuery.trim().toLowerCase();
                        const slotMatchEntries = normalizedSlotAssetQuery
                          ? workspaceProductImageAssetEntries
                              .filter((entry) => entry.searchText.includes(normalizedSlotAssetQuery))
                              .slice(0, 6)
                          : [];
                        const selectedImageUrl =
                          publicAssetBaseUrl && selectedAssetPublicId
                            ? `${publicAssetBaseUrl}/public/assets/${selectedAssetPublicId}`
                            : undefined;
                        const selectedImageErrored = Boolean(
                          selectedAssetPublicId && templateAssetPickerImageErrorsByPublicId[selectedAssetPublicId]
                        );
                        return (
                          <div key={slot.path} className="space-y-2 rounded-md border border-border bg-surface p-2">
                            <div className="text-xs font-semibold text-content">{readableSlotLabel}</div>
                            <div className="text-[11px] font-mono break-all text-content">{slot.path}</div>
                            <div className="flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
                              {slot.role ? <span>role: {slot.role}</span> : null}
                              {slot.recommendedAspect ? <span>aspect: {slot.recommendedAspect}</span> : null}
                            </div>
                            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
                              <Input
                                value={slotAssetQuery}
                                onChange={(event) => {
                                  const nextValue = event.target.value;
                                  setTemplateSlotAssetQueryByPath((current) => ({
                                    ...current,
                                    [slot.path]: nextValue,
                                  }));
                                  setTemplateDraftEditError(null);
                                }}
                                placeholder="Type asset UUID/public_id or product name"
                              />
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => {
                                  const normalizedQuery = slotAssetQuery.trim().toLowerCase();
                                  if (!normalizedQuery) {
                                    handleTemplateDraftSlotAssetChange(slot.path, "");
                                    setTemplateSlotAssetQueryByPath((current) => ({
                                      ...current,
                                      [slot.path]: "",
                                    }));
                                    return;
                                  }
                                  const exactPublicIdMatch = workspaceProductImageAssetEntries.find(
                                    (entry) => entry.asset.public_id.toLowerCase() === normalizedQuery
                                  );
                                  if (exactPublicIdMatch) {
                                    handleTemplateDraftSlotAssetChange(slot.path, exactPublicIdMatch.asset.public_id);
                                    setTemplateSlotAssetQueryByPath((current) => ({
                                      ...current,
                                      [slot.path]: exactPublicIdMatch.asset.public_id,
                                    }));
                                    return;
                                  }
                                  if (slotMatchEntries.length === 1) {
                                    handleTemplateDraftSlotAssetChange(slot.path, slotMatchEntries[0].asset.public_id);
                                    setTemplateSlotAssetQueryByPath((current) => ({
                                      ...current,
                                      [slot.path]: slotMatchEntries[0].asset.public_id,
                                    }));
                                    return;
                                  }
                                  if (!slotMatchEntries.length) {
                                    setTemplateDraftEditError(`No asset matched "${slotAssetQuery.trim()}".`);
                                    return;
                                  }
                                  setTemplateDraftEditError("Multiple assets matched. Select one from suggestions below.");
                                }}
                              >
                                Apply
                              </Button>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => {
                                  handleTemplateDraftSlotAssetChange(slot.path, "");
                                  setTemplateSlotAssetQueryByPath((current) => ({
                                    ...current,
                                    [slot.path]: "",
                                  }));
                                }}
                              >
                                Clear
                              </Button>
                            </div>
                            {normalizedSlotAssetQuery ? (
                              slotMatchEntries.length ? (
                                <div className="space-y-1 rounded-md border border-border bg-surface-2 p-2">
                                  <div className="text-[11px] font-semibold text-content">
                                    Matches ({slotMatchEntries.length})
                                  </div>
                                  {slotMatchEntries.map((entry) => (
                                    <button
                                      key={`${slot.path}-${entry.asset.id}`}
                                      type="button"
                                      className={cn(
                                        "w-full rounded border px-2 py-1 text-left text-[11px] transition",
                                        "border-border bg-surface hover:bg-surface-2"
                                      )}
                                      onClick={() => {
                                        handleTemplateDraftSlotAssetChange(slot.path, entry.asset.public_id);
                                        setTemplateSlotAssetQueryByPath((current) => ({
                                          ...current,
                                          [slot.path]: entry.asset.public_id,
                                        }));
                                      }}
                                    >
                                      <div className="truncate font-semibold text-content">{entry.productTitle}</div>
                                      <div className="font-mono text-content-muted">{entry.asset.public_id}</div>
                                    </button>
                                  ))}
                                </div>
                              ) : (
                                <div className="text-[11px] text-danger">No assets match this input.</div>
                              )
                            ) : null}
                            {selectedAssetPublicId ? (
                              <div className="space-y-1 rounded-md border border-border bg-surface-2 p-2">
                                <div className="rounded-md border border-border bg-surface p-1">
                                  {selectedImageUrl && !selectedImageErrored ? (
                                    <img
                                      src={selectedImageUrl}
                                      alt={slot.path}
                                      className="h-28 w-full rounded object-contain"
                                      onError={() =>
                                        setTemplateAssetPickerImageErrorsByPublicId((current) => ({
                                          ...current,
                                          [selectedAssetPublicId]: true,
                                        }))
                                      }
                                    />
                                  ) : (
                                    <div className="grid h-28 place-items-center text-xs text-content-muted">
                                      Preview unavailable.
                                    </div>
                                  )}
                                </div>
                                {selectedAssetEntry ? (
                                  <div className="text-[11px] text-content-muted">
                                    {selectedAssetEntry.productTitle} · {selectedAssetEntry.dimensions} ·{" "}
                                    {selectedAssetEntry.createdAtLabel}
                                  </div>
                                ) : (
                                  <div className="text-[11px] text-content-muted">
                                    Asset is not in the current workspace product image list.
                                  </div>
                                )}
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>

                    <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                      <div className="text-xs font-semibold text-content">Search results</div>
                      {filteredWorkspaceProductImageAssetEntries.length ? (
                        filteredWorkspaceProductImageAssetEntries.map((entry) => {
                          const { asset } = entry;
                          const assetImageUrl = publicAssetBaseUrl
                            ? `${publicAssetBaseUrl}/public/assets/${asset.public_id}`
                            : undefined;
                          const assetImageErrored = Boolean(
                            templateAssetPickerImageErrorsByPublicId[asset.public_id]
                          );
                          return (
                            <div
                              key={asset.id}
                              className="grid grid-cols-[88px_minmax(0,1fr)] gap-2 rounded-md border border-border bg-surface p-2"
                            >
                              <div className="rounded-md border border-border bg-surface p-1">
                                {assetImageUrl && !assetImageErrored ? (
                                  <img
                                    src={assetImageUrl}
                                    alt={asset.public_id}
                                    className="h-20 w-full rounded object-contain"
                                    onError={() =>
                                      setTemplateAssetPickerImageErrorsByPublicId((current) => ({
                                        ...current,
                                        [asset.public_id]: true,
                                      }))
                                    }
                                  />
                                ) : (
                                  <div className="grid h-20 place-items-center text-[11px] text-content-muted">
                                    No preview
                                  </div>
                                )}
                              </div>
                              <div className="min-w-0 space-y-1">
                                <div className="text-xs font-semibold text-content truncate">{entry.productTitle}</div>
                                <div className="text-[11px] font-mono text-content break-all">
                                  {asset.public_id}
                                </div>
                                <div className="text-[11px] text-content-muted">
                                  {entry.dimensions} · {entry.createdAtLabel} · {asset.status}
                                </div>
                                {entry.tagsLabel ? (
                                  <div className="text-[11px] text-content-muted truncate">tags: {entry.tagsLabel}</div>
                                ) : null}
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                          No assets match this search.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
            */}
            {/* Slot summary */}
            <div className="flex items-center justify-between rounded-md border border-divider bg-surface-2 px-3 py-2">
              <div className="text-xs text-content-muted">
                <span className="font-semibold text-content">{selectedTemplateDraft.latestVersion.data.imageSlots.length}</span> image slots ·{" "}
                <span className="font-semibold text-content">{selectedTemplateDraft.latestVersion.data.textSlots.length}</span> text slots · Auto-saves
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleOpenMappedImageSlotsModal}
                >
                  View mapped slots
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    void handleClearTemplateDraftImageMappings();
                  }}
                  disabled={updateShopifyThemeTemplateDraft.isPending}
                >
                  {updateShopifyThemeTemplateDraft.isPending ? "Clearing\u2026" : "Clear mappings"}
                </Button>
              </div>
            </div>

            {templateDraftEditError ? <div className="text-xs text-danger">{templateDraftEditError}</div> : null}

            {/* Actions */}
            <div className="flex items-center gap-2 border-t border-divider pt-3">
              <Button
                size="sm"
                onClick={() => {
                  void handleGenerateTemplateDraftImages();
                }}
                disabled={generateShopifyThemeTemplateImages.isPending}
              >
                {generateShopifyThemeTemplateImages.isPending
                  ? "Generating\u2026"
                  : "Generate images + text"}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={handleOpenTemplatePreview}
              >
                Preview
              </Button>
              <div className="flex-1" />
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  void handleDownloadTemplateZip();
                }}
                disabled={
                  downloadShopifyThemeTemplateZip.isPending ||
                  updateShopifyThemeTemplateDraft.isPending ||
                  !selectedTemplateDraftId.trim()
                }
              >
                {downloadShopifyThemeTemplateZip.isPending
                  ? "Preparing ZIP\u2026"
                  : updateShopifyThemeTemplateDraft.isPending
                    ? "Saving draft\u2026"
                    : "Download ZIP"}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between rounded-md border border-dashed border-divider bg-surface-2 px-3 py-3">
            <div className="text-xs text-content-muted">
              No template drafts yet. Create one to start generating content.
            </div>
            <Button
              size="sm"
              onClick={() => {
                void handleCreateBaseTemplateDraft();
              }}
              disabled={buildShopifyThemeTemplateDraft.isPending}
            >
              {buildShopifyThemeTemplateDraft.isPending
                ? "Creating\u2026"
                : "Create draft"}
            </Button>
          </div>
        )}

      </div>

      {/* MappedImageSlotsDialog */}
      <DialogRoot open={mappedImageSlotsDialogOpen} onOpenChange={setMappedImageSlotsDialogOpen}>
        <DialogContent className="max-w-3xl">
          <div className="space-y-2">
            <DialogTitle>Mapped image slots</DialogTitle>
            <DialogDescription>
              Clear one mapped image slot without clearing all mappings.
            </DialogDescription>
          </div>

          <div className="mt-4">
            {parsedTemplateDraftImageMapResult.error ? (
              <div className="rounded-md border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                {parsedTemplateDraftImageMapResult.error}
              </div>
            ) : !mappedTemplateImageSlotEntries.length ? (
              <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                No mapped image slots yet.
              </div>
            ) : (
              <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
                {mappedTemplateImageSlotEntries.map((entry) => {
                  const isClearingThisSlot =
                    updateShopifyThemeTemplateDraft.isPending &&
                    clearingTemplateDraftImageSlotPath === entry.path;
                  return (
                    <div
                      key={`mapped-slot-modal-${entry.path}`}
                      className="space-y-2 rounded-md border border-border bg-surface p-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-xs font-semibold text-content">
                          {entry.readableSlotLabel}
                        </div>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            void handleClearTemplateDraftImageMapping(entry.path);
                          }}
                          disabled={updateShopifyThemeTemplateDraft.isPending}
                        >
                          {isClearingThisSlot ? "Clearing\u2026" : "Clear slot"}
                        </Button>
                      </div>
                      <div className="text-[11px] font-mono break-all text-content">
                        {entry.path}
                      </div>
                      <div className="text-[11px] font-mono break-all text-content-muted">
                        asset: {entry.assetPublicId}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
                        {entry.role ? <span>role: {entry.role}</span> : null}
                        {entry.recommendedAspect ? (
                          <span>aspect: {entry.recommendedAspect}</span>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </DialogRoot>

      {/* TemplatePreviewDialog */}
      <DialogRoot
        open={templatePreviewDialogOpen}
        onOpenChange={setTemplatePreviewDialogOpen}
      >
        <DialogContent className="max-w-5xl">
          <div className="space-y-2">
            <DialogTitle>Template Draft Preview</DialogTitle>
            <DialogDescription>
              Review mapped images and text before exporting this template ZIP.
            </DialogDescription>
          </div>

          {!selectedTemplateDraft?.latestVersion ? (
            <div className="mt-4 rounded-md border border-border bg-surface-2 p-4 text-sm text-content-muted">
              Select a template draft to preview.
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              {!publicAssetBaseUrl ? (
                <div className="rounded-md border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                  Missing `VITE_API_BASE_URL`; image previews cannot be loaded.
                </div>
              ) : null}

              <div className="space-y-2">
                <div className="text-xs font-semibold text-content">Mapped images</div>
                {templatePreviewImageItems.length ? (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 max-h-[48vh] overflow-y-auto pr-1">
                    {templatePreviewImageItems.map((item) => {
                      const imageUrl =
                        publicAssetBaseUrl && item.assetPublicId
                          ? `${publicAssetBaseUrl}/public/assets/${item.assetPublicId}`
                          : undefined;
                      const loadErrored = Boolean(templatePreviewImageErrorsByPath[item.path]);
                      const readableSlotLabel =
                        templateImageSlotReadableLabelByPath.get(item.path) ||
                        humanizeSlotToken(item.path.split(".").pop() || item.path);
                      return (
                        <div key={item.path} className="rounded-md border border-border bg-surface p-3 space-y-2">
                          <div className="text-xs font-semibold text-content">{readableSlotLabel}</div>
                          <div className="text-[11px] font-mono break-all text-content">{item.path}</div>
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
                            {item.role ? <span>role: {item.role}</span> : null}
                            {item.recommendedAspect ? <span>aspect: {item.recommendedAspect}</span> : null}
                            {!item.hasKnownSlot ? <span>custom path</span> : null}
                          </div>
                          <div className="rounded-md border border-border bg-surface-2 p-2">
                            {imageUrl && !loadErrored ? (
                              <img
                                src={imageUrl}
                                alt={item.path}
                                className="h-44 w-full rounded object-contain bg-surface"
                                onError={() =>
                                  setTemplatePreviewImageErrorsByPath((current) => ({
                                    ...current,
                                    [item.path]: true,
                                  }))
                                }
                              />
                            ) : (
                              <div className="grid h-44 place-items-center text-xs text-content-muted">
                                {item.assetPublicId
                                  ? "Image could not be loaded."
                                  : "No mapped asset for this slot."}
                              </div>
                            )}
                          </div>
                          <div className="text-[11px] text-content-muted break-all">
                            asset: <span className="font-mono text-content">{item.assetPublicId || "n/a"}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    No image mappings found in this draft.
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold text-content">Mapped text values</div>
                {templatePreviewTextEntries.length ? (
                  <Table variant="ghost" size={1} layout="fixed" containerClassName="rounded-md border border-divider">
                    <TableHeader>
                      <TableRow>
                        <TableHeadCell className="w-[55%]">Path</TableHeadCell>
                        <TableHeadCell>Value</TableHeadCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {templatePreviewTextEntries.map(([path, value]) => (
                        <TableRow key={path}>
                          <TableCell className="font-mono text-[11px] text-content break-all">{path}</TableCell>
                          <TableCell className="text-xs text-content break-all">{value}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    No text mappings found in this draft.
                  </div>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </DialogRoot>
    </>
  );
}
