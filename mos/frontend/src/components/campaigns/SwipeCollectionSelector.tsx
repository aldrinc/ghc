import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  SWIPE_COLLECTIONS_QUERY_KEY,
  swipeCollectionDetailQueryKey,
  useCompanySwipes,
  useSwipeCollection,
  useSwipeCollections,
  useSwipeCollectionsApi,
} from "@/api/swipes";
import {
  CAMPAIGN_SWIPE_COLLECTION_QUERY_KEY,
  useCampaignSwipeCollection,
  useUpdateCampaignSwipeCollection,
} from "@/api/campaigns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  formatSwipeAssetTypeLabel,
  matchesSwipeAssetTypeFilter,
  normalizeSwipeToLibraryItem,
  resolveSwipeAssetType,
} from "@/lib/library";
import { cn } from "@/lib/utils";
import type { CompanySwipeAsset, SwipeAssetTypeFilter, SwipeCollection } from "@/types/swipes";

const CREATE_KIND_OPTIONS = [
  { label: "Curated", value: "curated" },
  { label: "Uploaded", value: "uploaded" },
] as const;

const SWIPE_ASSET_TYPE_FILTER_OPTIONS = [
  { label: "All asset types", value: "all" },
  { label: "Static images", value: "image" },
  { label: "Videos", value: "video" },
  { label: "Carousels", value: "carousel" },
  { label: "Unknown", value: "unknown" },
] as const;

type SwipeCollectionSelectorProps = {
  campaignId: string;
  value: string | null;
  onChange: (value: string) => void;
  className?: string;
  title?: string;
  description?: string;
};

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

function resolvePreferredCollectionId(collections: SwipeCollection[], preferredId?: string | null) {
  if (!collections.length) return "";
  if (preferredId && collections.some((collection) => collection.id === preferredId)) {
    return preferredId;
  }
  return collections.find((collection) => collection.kind === "uploaded" || collection.kind === "curated")?.id || "";
}

function formatCollectionKind(kind?: string | null) {
  if (!kind) return "Unknown";
  if (kind === "default") return "Default";
  if (kind === "uploaded") return "Uploaded";
  if (kind === "curated") return "Curated";
  return kind.replace(/_/g, " ");
}

function resolveSwipePreviewUrl(swipe: CompanySwipeAsset): string | undefined {
  const item = normalizeSwipeToLibraryItem(swipe);
  return item.media[0]?.thumbUrl || item.media[0]?.url;
}

function describeSwipe(swipe: CompanySwipeAsset) {
  return swipe.title?.trim() || swipe.body?.trim() || `Swipe ${swipe.id.slice(0, 8)}`;
}

function matchesSwipeSearch(swipe: CompanySwipeAsset, searchTerm: string) {
  if (!searchTerm) return true;
  const haystack = [
    swipe.title,
    swipe.body,
    swipe.channel,
    swipe.destination_type,
    swipe.funnel_stage,
    swipe.angle_family,
    swipe.hook_type,
    swipe.id,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(searchTerm);
}

function SwipeAssetRow({
  swipe,
  checked,
  onCheckedChange,
  action,
  disabled = false,
}: {
  swipe: CompanySwipeAsset;
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  action?: ReactNode;
  disabled?: boolean;
}) {
  const previewUrl = resolveSwipePreviewUrl(swipe);
  const assetType = resolveSwipeAssetType(swipe);

  return (
    <label
      className={cn(
        "flex items-start gap-3 rounded-lg border border-border bg-surface-2 px-3 py-3",
        onCheckedChange && !disabled ? "cursor-pointer" : "",
        disabled ? "opacity-60" : "",
      )}
    >
      {onCheckedChange ? (
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 rounded border border-border bg-surface text-accent"
          checked={Boolean(checked)}
          disabled={disabled}
          onChange={(event) => onCheckedChange(event.target.checked)}
        />
      ) : null}
      {previewUrl ? (
        <img
          src={previewUrl}
          alt={describeSwipe(swipe)}
          className="h-16 w-16 rounded-md border border-border object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-16 w-16 items-center justify-center rounded-md border border-dashed border-border bg-surface text-[10px] uppercase tracking-wide text-content-muted">
          No media
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-content">{describeSwipe(swipe)}</div>
        <div className="mt-1 line-clamp-2 text-xs text-content-muted">
          {swipe.body?.trim() || "No body copy stored."}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {swipe.analysis_status ? <Badge tone={swipe.analysis_status === "ready" ? "success" : "neutral"}>{swipe.analysis_status}</Badge> : null}
          <Badge tone="neutral">{formatSwipeAssetTypeLabel(assetType)}</Badge>
          {swipe.channel ? <Badge tone="neutral">{swipe.channel}</Badge> : null}
          {swipe.funnel_stage ? <Badge tone="neutral">{swipe.funnel_stage}</Badge> : null}
          <Badge tone="neutral">{swipe.id.slice(0, 8)}</Badge>
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </label>
  );
}

export function SwipeCollectionSelector({
  campaignId,
  value,
  onChange,
  className,
  title = "Swipe collection",
  description = "Creative production requires an explicit swipe collection. Choose, clone, or curate the set used for generation.",
}: SwipeCollectionSelectorProps) {
  const queryClient = useQueryClient();
  const { createSwipeCollection, cloneSwipeCollection, addSwipesToCollection, removeSwipeFromCollection } =
    useSwipeCollectionsApi();
  const {
    data: collections = [],
    isLoading: collectionsLoading,
    error: collectionsError,
  } = useSwipeCollections();
  const {
    data: campaignDefaultCollection,
    isLoading: campaignDefaultLoading,
  } = useCampaignSwipeCollection(campaignId);
  const updateCampaignSwipeCollection = useUpdateCampaignSwipeCollection(campaignId);

  const selectedCollection = useMemo(
    () => collections.find((collection) => collection.id === value) ?? null,
    [collections, value],
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [cloneOpen, setCloneOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createKind, setCreateKind] = useState<"uploaded" | "curated">("curated");
  const [cloneName, setCloneName] = useState("");
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [createPending, setCreatePending] = useState(false);
  const [clonePending, setClonePending] = useState(false);
  const [selectedAvailableSwipeIds, setSelectedAvailableSwipeIds] = useState<string[]>([]);
  const [availableSearch, setAvailableSearch] = useState("");
  const [collectionSearch, setCollectionSearch] = useState("");
  const [availableAssetTypeFilter, setAvailableAssetTypeFilter] = useState<SwipeAssetTypeFilter>("all");
  const [collectionAssetTypeFilter, setCollectionAssetTypeFilter] = useState<SwipeAssetTypeFilter>("all");
  const [addPending, setAddPending] = useState(false);
  const [removingSwipeIds, setRemovingSwipeIds] = useState<string[]>([]);

  const {
    data: collectionDetail,
    isLoading: collectionDetailLoading,
    error: collectionDetailError,
  } = useSwipeCollection(value, manageOpen);
  const {
    data: companySwipes = [],
    isLoading: companySwipesLoading,
    error: companySwipesError,
  } = useCompanySwipes(undefined, manageOpen && Boolean(selectedCollection?.writable));

  // Sync with campaign's persisted default swipe collection (backend state)
  useEffect(() => {
    if (collectionsLoading || campaignDefaultLoading) return;
    if (!collections.length) {
      if (value) onChange("");
      return;
    }
    const currentIsValid = Boolean(value) && collections.some((collection) => collection.id === value);
    if (currentIsValid) return;
    const defaultId = campaignDefaultCollection?.swipeCollectionId ?? null;
    if (!defaultId) {
      if (value) onChange("");
      return;
    }
    const nextValue = resolvePreferredCollectionId(collections, defaultId);
    if (nextValue !== value) {
      onChange(nextValue);
    }
  }, [campaignId, collections, collectionsLoading, campaignDefaultLoading, campaignDefaultCollection, onChange, value]);

  // Persist selection to campaign when user explicitly changes it
  const handleCollectionChange = (newCollectionId: string) => {
    onChange(newCollectionId);
    updateCampaignSwipeCollection.mutate(newCollectionId || null);
  };

  useEffect(() => {
    if (!manageOpen) {
      setAvailableSearch("");
      setCollectionSearch("");
      setAvailableAssetTypeFilter("all");
      setCollectionAssetTypeFilter("all");
      setSelectedAvailableSwipeIds([]);
      return;
    }
    setSelectedAvailableSwipeIds((current) =>
      current.filter((swipeId) => !(collectionDetail?.swipes || []).some((swipe) => swipe.id === swipeId)),
    );
  }, [collectionDetail?.swipes, manageOpen]);

  const collectionOptions = useMemo(
    () => [
      {
        label: collectionsLoading
          ? "Loading swipe collections…"
          : collections.length
          ? "Select a swipe collection"
          : "No swipe collections available",
        value: "",
        disabled: true,
      },
      ...collections.map((collection) => {
        const readyCount = collection.analysis_counts.ready || 0;
        const badges = [`${collection.item_count} swipes`, `${readyCount} ready`];
        const launchable = collection.kind === "uploaded" || collection.kind === "curated";
        if (!collection.writable) badges.push("read-only");
        if (!launchable) badges.push("not launchable");
        return {
          label: `${collection.name} · ${badges.join(" · ")}`,
          value: collection.id,
          disabled: !launchable,
        };
      }),
    ],
    [collections, collectionsLoading],
  );

  const currentCollectionSwipes = collectionDetail?.swipes || [];
  const currentCollectionSwipeIds = useMemo(
    () => new Set(currentCollectionSwipes.map((swipe) => swipe.id)),
    [currentCollectionSwipes],
  );
  const filteredCollectionSwipes = useMemo(() => {
    const searchTerm = collectionSearch.trim().toLowerCase();
    return currentCollectionSwipes
      .filter((swipe) => matchesSwipeSearch(swipe, searchTerm))
      .filter((swipe) => matchesSwipeAssetTypeFilter(swipe, collectionAssetTypeFilter));
  }, [collectionAssetTypeFilter, collectionSearch, currentCollectionSwipes]);
  const filteredAvailableSwipes = useMemo(() => {
    const searchTerm = availableSearch.trim().toLowerCase();
    return companySwipes
      .filter((swipe) => !currentCollectionSwipeIds.has(swipe.id))
      .filter((swipe) => matchesSwipeSearch(swipe, searchTerm))
      .filter((swipe) => matchesSwipeAssetTypeFilter(swipe, availableAssetTypeFilter))
      .slice(0, 60);
  }, [availableAssetTypeFilter, availableSearch, companySwipes, currentCollectionSwipeIds]);

  const invalidateCollectionData = async (collectionId?: string | null) => {
    await queryClient.invalidateQueries({ queryKey: SWIPE_COLLECTIONS_QUERY_KEY });
    if (collectionId) {
      await queryClient.invalidateQueries({ queryKey: swipeCollectionDetailQueryKey(collectionId) });
    }
    await queryClient.invalidateQueries({ queryKey: ["swipes", "company"] });
    // Also invalidate campaign swipe collection
    if (campaignId) {
      await queryClient.invalidateQueries({ queryKey: CAMPAIGN_SWIPE_COLLECTION_QUERY_KEY(campaignId) });
    }
  };

  const handleCreateCollection = async () => {
    setMutationError(null);
    const name = createName.trim();
    if (!name) {
      setMutationError("Collection name is required.");
      return;
    }
    setCreatePending(true);
    try {
      const created = await createSwipeCollection({ name, kind: createKind });
      await invalidateCollectionData(created.id);
      // Persist as campaign default when creating new collection
      await updateCampaignSwipeCollection.mutateAsync(created.id);
      onChange(created.id);
      setCreateName("");
      setCreateKind("curated");
      setCreateOpen(false);
      setManageOpen(true);
    } catch (err) {
      setMutationError(getErrorMessage(err));
    } finally {
      setCreatePending(false);
    }
  };

  const handleCloneCollection = async () => {
    if (!selectedCollection) {
      setMutationError("Select a collection before cloning it.");
      return;
    }
    setMutationError(null);
    const name = cloneName.trim();
    if (!name) {
      setMutationError("Clone name is required.");
      return;
    }
    setClonePending(true);
    try {
      const cloned = await cloneSwipeCollection(selectedCollection.id, { name });
      await invalidateCollectionData(cloned.id);
      // Persist as campaign default when cloning collection
      await updateCampaignSwipeCollection.mutateAsync(cloned.id);
      onChange(cloned.id);
      setCloneName("");
      setCloneOpen(false);
      setManageOpen(true);
    } catch (err) {
      setMutationError(getErrorMessage(err));
    } finally {
      setClonePending(false);
    }
  };

  const handleAddSelectedSwipes = async () => {
    if (!selectedCollection) {
      setMutationError("Select a collection before adding swipes.");
      return;
    }
    if (!selectedAvailableSwipeIds.length) {
      setMutationError("Pick at least one swipe to add.");
      return;
    }
    setMutationError(null);
    setAddPending(true);
    try {
      await addSwipesToCollection(selectedCollection.id, { swipeAssetIds: selectedAvailableSwipeIds });
      await invalidateCollectionData(selectedCollection.id);
      setSelectedAvailableSwipeIds([]);
    } catch (err) {
      setMutationError(getErrorMessage(err));
    } finally {
      setAddPending(false);
    }
  };

  const handleRemoveSwipe = async (swipeAssetId: string) => {
    if (!selectedCollection) {
      setMutationError("Select a collection before removing swipes.");
      return;
    }
    setMutationError(null);
    setRemovingSwipeIds((current) => (current.includes(swipeAssetId) ? current : [...current, swipeAssetId]));
    try {
      await removeSwipeFromCollection(selectedCollection.id, swipeAssetId);
      await invalidateCollectionData(selectedCollection.id);
      setSelectedAvailableSwipeIds((current) => current.filter((id) => id !== swipeAssetId));
    } catch (err) {
      setMutationError(getErrorMessage(err));
    } finally {
      setRemovingSwipeIds((current) => current.filter((id) => id !== swipeAssetId));
    }
  };

  const selectedReadyCount = selectedCollection?.analysis_counts.ready || 0;

  return (
    <>
      <div className={cn("rounded-xl border border-border bg-surface p-4", className)}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">{title}</div>
            <div className="mt-1 text-sm text-content-muted">{description}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => setCreateOpen(true)}>
              Create collection
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setCloneName(selectedCollection ? `${selectedCollection.name} copy` : "");
                setCloneOpen(true);
              }}
              disabled={!selectedCollection}
            >
              Clone selected
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setManageOpen(true)} disabled={!selectedCollection}>
              Manage swipes
            </Button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
          <Select
            value={value || ""}
            options={collectionOptions}
            onValueChange={handleCollectionChange}
            disabled={collectionsLoading || collections.length === 0}
          />
          {selectedCollection ? (
            <div className="flex flex-wrap gap-2">
              <Badge tone="neutral">{formatCollectionKind(selectedCollection.kind)}</Badge>
              <Badge tone={selectedCollection.writable ? "success" : "neutral"}>
                {selectedCollection.writable ? "Writable" : "Read-only"}
              </Badge>
              <Badge tone="neutral">{selectedCollection.item_count} swipes</Badge>
              <Badge tone={selectedReadyCount > 0 ? "success" : "neutral"}>{selectedReadyCount} ready</Badge>
            </div>
          ) : null}
        </div>

        {!selectedCollection && !collectionsLoading ? (
          <Callout variant="warning" size="sm" className="mt-3" title="Swipe collection required">
            Create or select a swipe collection before starting creative production.
          </Callout>
        ) : null}

        {collectionsError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Failed to load swipe collections">
            {getErrorMessage(collectionsError)}
          </Callout>
        ) : null}
        {mutationError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Collection update failed">
            {mutationError}
          </Callout>
        ) : null}
      </div>

      <DialogRoot open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogTitle>Create swipe collection</DialogTitle>
          <DialogDescription>
            Start a curated collection for campaign-specific swipe selection.
          </DialogDescription>
          <div className="mt-4 space-y-4">
            <div>
              <div className="mb-2 text-sm font-medium text-content">Name</div>
              <Input
                value={createName}
                onChange={(event) => setCreateName(event.target.value)}
                placeholder="Honest Herbalist shortlist"
              />
            </div>
            <div>
              <div className="mb-2 text-sm font-medium text-content">Kind</div>
              <Select
                value={createKind}
                options={CREATE_KIND_OPTIONS.map((option) => ({ ...option }))}
                onValueChange={(nextValue) => setCreateKind(nextValue as "uploaded" | "curated")}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setCreateOpen(false)} disabled={createPending}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" onClick={() => void handleCreateCollection()} disabled={createPending}>
                {createPending ? "Creating…" : "Create collection"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </DialogRoot>

      <DialogRoot open={cloneOpen} onOpenChange={setCloneOpen}>
        <DialogContent>
          <DialogTitle>Clone swipe collection</DialogTitle>
          <DialogDescription>
            Clone the current collection into a writable set before curating it.
          </DialogDescription>
          <div className="mt-4 space-y-4">
            <div>
              <div className="mb-2 text-sm font-medium text-content">Source</div>
              <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-content-muted">
                {selectedCollection?.name || "No collection selected"}
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-medium text-content">Clone name</div>
              <Input
                value={cloneName}
                onChange={(event) => setCloneName(event.target.value)}
                placeholder="Honest Herbalist curated v2"
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setCloneOpen(false)} disabled={clonePending}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleCloneCollection()}
                disabled={clonePending || !selectedCollection}
              >
                {clonePending ? "Cloning…" : "Clone collection"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </DialogRoot>

      <DialogRoot open={manageOpen} onOpenChange={setManageOpen}>
        <DialogContent className="max-w-6xl">
          <DialogTitle>Manage swipe collection</DialogTitle>
          <DialogDescription>
            Review the exact swipes that creative production will use for this campaign.
          </DialogDescription>

          {selectedCollection ? (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Badge tone="neutral">{selectedCollection.name}</Badge>
              <Badge tone="neutral">{formatCollectionKind(selectedCollection.kind)}</Badge>
              <Badge tone={selectedCollection.writable ? "success" : "neutral"}>
                {selectedCollection.writable ? "Writable" : "Read-only"}
              </Badge>
              <Badge tone="neutral">{selectedCollection.item_count} swipes</Badge>
              <Badge tone={selectedReadyCount > 0 ? "success" : "neutral"}>{selectedReadyCount} ready</Badge>
            </div>
          ) : null}

          {collectionDetailError ? (
            <Callout variant="danger" size="sm" className="mt-4" title="Failed to load collection">
              {getErrorMessage(collectionDetailError)}
            </Callout>
          ) : null}
          {mutationError ? (
            <Callout variant="danger" size="sm" className="mt-4" title="Collection update failed">
              {mutationError}
            </Callout>
          ) : null}

          {collectionDetailLoading ? (
            <div className="mt-4 rounded-lg border border-border bg-surface-2 px-4 py-6 text-sm text-content-muted">
              Loading collection detail…
            </div>
          ) : (
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <div className="rounded-xl border border-border bg-surface p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-content">Current swipes</div>
                    <div className="text-xs text-content-muted">
                      {currentCollectionSwipes.length} swipe{currentCollectionSwipes.length === 1 ? "" : "s"} in this collection.
                    </div>
                  </div>
                  <Badge tone="neutral">{currentCollectionSwipes.length}</Badge>
                </div>
                <Input
                  className="mt-3"
                  value={collectionSearch}
                  onChange={(event) => setCollectionSearch(event.target.value)}
                  placeholder="Filter current swipes"
                />
                <div className="mt-2">
                  <Select
                    value={collectionAssetTypeFilter}
                    onValueChange={(value) => setCollectionAssetTypeFilter(value as SwipeAssetTypeFilter)}
                    options={SWIPE_ASSET_TYPE_FILTER_OPTIONS.map((option) => ({ ...option }))}
                  />
                </div>
                <div className="mt-3 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                  {filteredCollectionSwipes.length ? (
                    filteredCollectionSwipes.map((swipe) => (
                      <SwipeAssetRow
                        key={swipe.id}
                        swipe={swipe}
                        action={
                          selectedCollection?.writable ? (
                            <Button
                              variant="secondary"
                              size="sm"
                              disabled={removingSwipeIds.includes(swipe.id)}
                              onClick={() => void handleRemoveSwipe(swipe.id)}
                            >
                              {removingSwipeIds.includes(swipe.id) ? "Removing…" : "Remove"}
                            </Button>
                          ) : undefined
                        }
                      />
                    ))
                  ) : (
                    <div className="rounded-lg border border-dashed border-border bg-surface-2 px-4 py-6 text-sm text-content-muted">
                      No swipes matched this filter.
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-border bg-surface p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-content">Add swipes</div>
                    <div className="text-xs text-content-muted">
                      Curate this collection from the saved company swipe library.
                    </div>
                  </div>
                  <Badge tone="neutral">{selectedAvailableSwipeIds.length} selected</Badge>
                </div>

                {!selectedCollection?.writable ? (
                  <Callout variant="warning" size="sm" className="mt-3" title="This collection is read-only">
                    Clone the selected collection before adding or removing swipes.
                  </Callout>
                ) : companySwipesError ? (
                  <Callout variant="danger" size="sm" className="mt-3" title="Failed to load saved swipes">
                    {getErrorMessage(companySwipesError)}
                  </Callout>
                ) : (
                  <>
                    <Input
                      className="mt-3"
                      value={availableSearch}
                      onChange={(event) => setAvailableSearch(event.target.value)}
                      placeholder="Filter saved swipes"
                    />
                    <div className="mt-2">
                      <Select
                        value={availableAssetTypeFilter}
                        onValueChange={(value) => setAvailableAssetTypeFilter(value as SwipeAssetTypeFilter)}
                        options={SWIPE_ASSET_TYPE_FILTER_OPTIONS.map((option) => ({ ...option }))}
                      />
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <div className="text-xs text-content-muted">
                        Showing up to {filteredAvailableSwipes.length} matching swipes not already in this collection.
                      </div>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => void handleAddSelectedSwipes()}
                        disabled={addPending || selectedAvailableSwipeIds.length === 0}
                      >
                        {addPending ? "Adding…" : "Add selected"}
                      </Button>
                    </div>
                    <div className="mt-3 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                      {companySwipesLoading ? (
                        <div className="rounded-lg border border-border bg-surface-2 px-4 py-6 text-sm text-content-muted">
                          Loading saved swipes…
                        </div>
                      ) : filteredAvailableSwipes.length ? (
                        filteredAvailableSwipes.map((swipe) => (
                          <SwipeAssetRow
                            key={swipe.id}
                            swipe={swipe}
                            checked={selectedAvailableSwipeIds.includes(swipe.id)}
                            onCheckedChange={(checked) => {
                              setSelectedAvailableSwipeIds((current) =>
                                checked
                                  ? current.includes(swipe.id)
                                    ? current
                                    : [...current, swipe.id]
                                  : current.filter((id) => id !== swipe.id),
                              );
                            }}
                          />
                        ))
                      ) : (
                        <div className="rounded-lg border border-dashed border-border bg-surface-2 px-4 py-6 text-sm text-content-muted">
                          No saved swipes are available for this filter.
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </DialogRoot>
    </>
  );
}
