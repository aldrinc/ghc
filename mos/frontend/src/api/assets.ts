import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "@/api/client";
import type { Asset } from "@/types/common";

type AssetFilters = {
  clientId?: string;
  campaignId?: string;
  experimentId?: string;
  productId?: string;
  funnelId?: string;
  assetKind?: string;
  tags?: string[];
  statuses?: string[];
};

const buildPath = (filters: AssetFilters) => {
  const params = new URLSearchParams();
  if (filters.clientId) params.set("clientId", filters.clientId);
  if (filters.campaignId) params.set("campaignId", filters.campaignId);
  if (filters.experimentId) params.set("experimentId", filters.experimentId);
  if (filters.productId) params.set("productId", filters.productId);
  if (filters.funnelId) params.set("funnelId", filters.funnelId);
  if (filters.assetKind) params.set("assetKind", filters.assetKind);
  (filters.tags || []).forEach((tag) => params.append("tags", tag));
  (filters.statuses || []).forEach((status) => params.append("statuses", status));
  const qs = params.toString();
  return qs ? `/assets?${qs}` : "/assets";
};

export function useAssets(filters: AssetFilters, opts?: { enabled?: boolean }) {
  const { get } = useApiClient();
  const enabled = opts?.enabled ?? Boolean(
    filters.clientId ||
      filters.campaignId ||
      filters.experimentId ||
      filters.productId ||
      filters.funnelId ||
      filters.assetKind ||
      (filters.tags && filters.tags.length) ||
      (filters.statuses && filters.statuses.length)
  );
  return useQuery<Asset[]>({
    queryKey: ["assets", filters],
    queryFn: () => get(buildPath(filters)),
    enabled,
  });
}

