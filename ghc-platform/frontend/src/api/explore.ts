import { useCallback } from "react";
import { useApiClient } from "./client";

export type ExploreAdsParams = {
  q?: string;
  channels?: string[];
  status?: string[];
  brandIds?: string[];
  clientId?: string;
  researchRunId?: string;
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

export type ExploreBrand = {
  brand_id: string;
  brand_name: string;
  primary_domain?: string | null;
  primary_website_url?: string | null;
  ad_count: number;
  active_count: number;
  inactive_count: number;
  unknown_count: number;
  channels: string[];
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  hidden?: boolean;
};

export type ExploreBrandsParams = {
  q?: string;
  clientId?: string;
  researchRunId?: string;
  includeHidden?: boolean;
  limit?: number;
  offset?: number;
  sort?: string;
  direction?: "asc" | "desc";
};

export type ExploreBrandsResponse = {
  items: ExploreBrand[];
  count: number;
  limit: number;
  offset: number;
};

export function useExploreApi() {
  const { get, post, request } = useApiClient();

  const listAds = useCallback(
    async (params?: ExploreAdsParams): Promise<ExploreAdsResponse> => {
      const search = new URLSearchParams();
      if (params?.q) search.set("q", params.q);
      params?.channels?.forEach((value) => search.append("channels", value));
      params?.status?.forEach((value) => search.append("status", value));
      params?.brandIds?.forEach((value) => search.append("brandIds", value));
      if (params?.clientId) search.set("clientId", params.clientId);
      if (params?.researchRunId) search.set("researchRunId", params.researchRunId);
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

  const listBrands = useCallback(
    async (params?: ExploreBrandsParams): Promise<ExploreBrandsResponse> => {
      const search = new URLSearchParams();
      if (params?.q) search.set("q", params.q);
      if (params?.clientId) search.set("clientId", params.clientId);
      if (params?.researchRunId) search.set("researchRunId", params.researchRunId);
      if (params?.includeHidden) search.set("includeHidden", "true");
      if (params?.limit !== undefined) search.set("limit", params.limit.toString());
      if (params?.offset !== undefined) search.set("offset", params.offset.toString());
      if (params?.sort) search.set("sort", params.sort);
      if (params?.direction) search.set("direction", params.direction);

      const qs = search.toString();
      const path = qs ? `/explore/brands?${qs}` : "/explore/brands";
      return get<ExploreBrandsResponse>(path);
    },
    [get],
  );

  const hideBrand = useCallback(
    async (brandId: string): Promise<void> => post(`/explore/brands/${brandId}/hide`),
    [post],
  );

  const unhideBrand = useCallback(
    async (brandId: string): Promise<void> =>
      request(`/explore/brands/${brandId}/hide`, { method: "DELETE" }),
    [request],
  );

  return { listAds, listBrands, hideBrand, unhideBrand };
}
