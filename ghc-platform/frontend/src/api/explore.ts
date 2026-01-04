import { useCallback } from "react";
import { useApiClient } from "./client";

export type ExploreAdsParams = {
  q?: string;
  channels?: string[];
  status?: string[];
  countryCodes?: string[];
  languageCodes?: string[];
  minDaysActive?: number;
  maxDaysActive?: number;
  startDateFrom?: string;
  startDateTo?: string;
  minVideoLength?: number;
  maxVideoLength?: number;
  limitPerBrand?: number;
  limit?: number;
  offset?: number;
  sort?: string;
  direction?: string;
};

export type ExploreAdsResponse = {
  items: any[];
  count: number;
  limit: number;
  offset: number;
};

export function useExploreApi() {
  const { get } = useApiClient();

  const listAds = useCallback(
    async (params?: ExploreAdsParams): Promise<ExploreAdsResponse> => {
      const search = new URLSearchParams();
      if (params?.q) search.set("q", params.q);
      params?.channels?.forEach((value) => search.append("channels", value));
      params?.status?.forEach((value) => search.append("status", value));
      params?.countryCodes?.forEach((value) => search.append("countryCodes", value));
      params?.languageCodes?.forEach((value) => search.append("languageCodes", value));
      if (params?.minDaysActive !== undefined) search.set("min_days_active", params.minDaysActive.toString());
      if (params?.maxDaysActive !== undefined) search.set("max_days_active", params.maxDaysActive.toString());
      if (params?.startDateFrom) search.set("start_date_from", params.startDateFrom);
      if (params?.startDateTo) search.set("start_date_to", params.startDateTo);
      if (params?.minVideoLength !== undefined) search.set("min_video_length", params.minVideoLength.toString());
      if (params?.maxVideoLength !== undefined) search.set("max_video_length", params.maxVideoLength.toString());
      if (params?.limitPerBrand !== undefined) search.set("limit_per_brand", params.limitPerBrand.toString());
      if (params?.limit !== undefined) search.set("limit", params.limit.toString());
      if (params?.offset !== undefined) search.set("offset", params.offset.toString());
      if (params?.sort) search.set("sort", params.sort);
      if (params?.direction) search.set("direction", params.direction);

      const qs = search.toString();
      const path = qs ? `/explore/ads?${qs}` : "/explore/ads";
      return get<ExploreAdsResponse>(path);
    },
    [get],
  );

  return { listAds };
}
