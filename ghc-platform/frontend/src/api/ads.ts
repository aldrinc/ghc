import { useCallback } from "react";
import { useApiClient } from "./client";

export type AdsListParams = {
  clientId?: string;
  researchRunId?: string;
  brandId?: string;
  limit?: number;
  channel?: string;
  status?: string;
};

export function useAdsApi() {
  const { get } = useApiClient();

  const listAds = useCallback(
    (params?: AdsListParams): Promise<any[]> => {
      const searchParams = new URLSearchParams();
      if (params?.clientId) searchParams.set("clientId", params.clientId);
      if (params?.researchRunId) searchParams.set("researchRunId", params.researchRunId);
      if (params?.brandId) searchParams.set("brandId", params.brandId);
      if (params?.limit) searchParams.set("limit", params.limit.toString());
      if (params?.channel) searchParams.set("channel", params.channel);
      if (params?.status) searchParams.set("status", params.status);
      const qs = searchParams.toString();
      const path = qs ? `/ads?${qs}` : "/ads";
      return get<any[]>(path);
    },
    [get],
  );

  return { listAds };
}
