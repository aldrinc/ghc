import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "./client";
import type { Artifact } from "@/types/artifacts";

type ArtifactFilters = {
  clientId?: string;
  campaignId?: string;
  type?: string;
};

const buildPath = (filters: ArtifactFilters) => {
  const params = new URLSearchParams();
  if (filters.clientId) params.set("clientId", filters.clientId);
  if (filters.campaignId) params.set("campaignId", filters.campaignId);
  if (filters.type) params.set("type", filters.type);
  const qs = params.toString();
  return qs ? `/artifacts?${qs}` : "/artifacts";
};

export function useArtifacts(filters: ArtifactFilters) {
  const { get } = useApiClient();
  const enabled = Boolean(filters.clientId || filters.campaignId || filters.type);

  return useQuery<Artifact[]>({
    queryKey: ["artifacts", filters],
    queryFn: () => get(buildPath(filters)),
    enabled,
  });
}

export function useLatestArtifact(filters: ArtifactFilters) {
  const query = useArtifacts(filters);
  const latest = useMemo(() => {
    const list = query.data || [];
    if (!list.length) return null;
    return [...list].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )[0];
  }, [query.data]);
  return { ...query, latest };
}
