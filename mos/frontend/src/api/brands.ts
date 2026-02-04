import { useCallback } from "react";
import { useApiClient } from "./client";

export type BrandRelationship = {
  relationship_id: string;
  relationship_type: string;
  source_type: string;
  source_id?: string | null;
  created_at?: string | null;
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

export type BrandRelationshipsParams = {
  q?: string;
  clientId: string;
  productId: string;
  relationshipType?: string;
  includeHidden?: boolean;
  limit?: number;
  offset?: number;
  sort?: string;
  direction?: "asc" | "desc";
};

export type BrandRelationshipsResponse = {
  items: BrandRelationship[];
  count: number;
  limit: number;
  offset: number;
};

export function useBrandRelationshipsApi() {
  const { get } = useApiClient();

  const listRelationships = useCallback(
    async (params: BrandRelationshipsParams): Promise<BrandRelationshipsResponse> => {
      const search = new URLSearchParams();
      if (params.q) search.set("q", params.q);
      search.set("clientId", params.clientId);
      search.set("productId", params.productId);
      if (params.relationshipType) search.set("relationshipType", params.relationshipType);
      if (params.includeHidden) search.set("includeHidden", "true");
      if (params.limit !== undefined) search.set("limit", params.limit.toString());
      if (params.offset !== undefined) search.set("offset", params.offset.toString());
      if (params.sort) search.set("sort", params.sort);
      if (params.direction) search.set("direction", params.direction);

      const qs = search.toString();
      const path = qs ? `/brands/relationships?${qs}` : "/brands/relationships";
      return get<BrandRelationshipsResponse>(path);
    },
    [get],
  );

  return { listRelationships };
}
