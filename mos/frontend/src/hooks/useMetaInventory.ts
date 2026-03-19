import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMetaApi } from "@/api/meta";
import type { ApiError } from "@/api/client";
import type {
  MetaRemoteAd,
  MetaRemoteAdSet,
  MetaRemoteCampaign,
  MetaRemoteCreative,
  MetaRemoteImage,
  MetaRemoteVideo,
} from "@/types/meta";

export type InventoryTab = "images" | "videos" | "creatives" | "campaigns" | "adsets" | "ads";

export type RemotePayload =
  | { data: MetaRemoteImage[] }
  | { data: MetaRemoteVideo[] }
  | { data: MetaRemoteCreative[] }
  | { data: MetaRemoteCampaign[] }
  | { data: MetaRemoteAdSet[] }
  | { data: MetaRemoteAd[] };

export const inventoryTabs: { key: InventoryTab; label: string }[] = [
  { key: "images", label: "Images" },
  { key: "videos", label: "Videos" },
  { key: "creatives", label: "Creatives" },
  { key: "campaigns", label: "Campaigns" },
  { key: "adsets", label: "Ad Sets" },
  { key: "ads", label: "Ads" },
];

export function useMetaInventory({
  workspaceId,
  configId,
  metaAdAccountId,
}: {
  workspaceId: string | undefined;
  configId: string | undefined;
  metaAdAccountId: string | undefined;
}) {
  const {
    listRemoteImages,
    listRemoteVideos,
    listRemoteCreatives,
    listRemoteCampaigns,
    listRemoteAdSets,
    listRemoteAds,
  } = useMetaApi();

  const [inventoryTab, setInventoryTab] = useState<InventoryTab>("images");
  const [inventory, setInventory] = useState<RemotePayload | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [inventoryFetchedAt, setInventoryFetchedAt] = useState<string | null>(null);
  const latestRequestIdRef = useRef(0);
  const isMountedRef = useRef(true);

  const inventoryFetcher = useMemo(() => {
    switch (inventoryTab) {
      case "videos":
        return listRemoteVideos;
      case "creatives":
        return listRemoteCreatives;
      case "campaigns":
        return listRemoteCampaigns;
      case "adsets":
        return listRemoteAdSets;
      case "ads":
        return listRemoteAds;
      case "images":
      default:
        return listRemoteImages;
    }
  }, [inventoryTab, listRemoteAds, listRemoteAdSets, listRemoteCampaigns, listRemoteCreatives, listRemoteImages, listRemoteVideos]);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const runInventoryRequest = useCallback(
    async ({ resetFetchedAt = false, clearInventory = false }: { resetFetchedAt?: boolean; clearInventory?: boolean } = {}) => {
      if (!metaAdAccountId || !workspaceId || !configId) return;

      const requestId = latestRequestIdRef.current + 1;
      latestRequestIdRef.current = requestId;

      if (resetFetchedAt) setInventoryFetchedAt(null);
      if (clearInventory) setInventory(null);
      setInventoryError(null);
      setInventoryLoading(true);

      try {
        const data = await inventoryFetcher({
          fetchAll: true,
          clientId: workspaceId,
          metaConfigId: configId,
          adAccountId: metaAdAccountId,
        });
        if (!isMountedRef.current || latestRequestIdRef.current !== requestId) return;
        setInventory(data);
        setInventoryFetchedAt(new Date().toISOString());
      } catch (err) {
        if (!isMountedRef.current || latestRequestIdRef.current !== requestId) return;
        setInventoryError((err as ApiError)?.message || "Failed to load Meta inventory");
        setInventory(null);
      } finally {
        if (!isMountedRef.current || latestRequestIdRef.current !== requestId) return;
        setInventoryLoading(false);
      }
    },
    [configId, inventoryFetcher, metaAdAccountId, workspaceId],
  );

  useEffect(() => {
    if (!metaAdAccountId || !workspaceId || !configId) {
      latestRequestIdRef.current += 1;
      setInventory(null);
      setInventoryError(null);
      setInventoryFetchedAt(null);
      setInventoryLoading(false);
      return;
    }
    void runInventoryRequest();
  }, [configId, metaAdAccountId, runInventoryRequest, workspaceId]);

  const refreshInventory = useCallback(() => {
    void runInventoryRequest({ resetFetchedAt: true, clearInventory: true });
  }, [runInventoryRequest]);

  return {
    inventoryTab,
    setInventoryTab,
    inventory,
    inventoryLoading,
    inventoryError,
    inventoryFetchedAt,
    refreshInventory,
  };
}
