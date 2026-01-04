import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "./client";
import type { Experiment } from "@/types/common";

export function useExperiments(filters: { clientId?: string; campaignId?: string } = {}) {
  const { get } = useApiClient();
  const enabled = Boolean(filters.clientId || filters.campaignId);

  const path = useMemo(() => {
    const params = new URLSearchParams();
    if (filters.clientId) params.set("clientId", filters.clientId);
    if (filters.campaignId) params.set("campaignId", filters.campaignId);
    const qs = params.toString();
    return qs ? `/experiments?${qs}` : "/experiments";
  }, [filters.clientId, filters.campaignId]);

  return useQuery<Experiment[]>({
    queryKey: ["experiments", filters],
    queryFn: () => get(path),
    enabled,
  });
}
