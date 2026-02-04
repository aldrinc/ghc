import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "./client";
import type { Experiment } from "@/types/common";

export function useExperiments(filters: { clientId?: string; productId?: string; campaignId?: string } = {}) {
  const { get } = useApiClient();
  const enabled = Boolean(filters.campaignId || (filters.clientId && filters.productId));

  const path = useMemo(() => {
    const params = new URLSearchParams();
    if (filters.clientId) params.set("clientId", filters.clientId);
    if (filters.productId) params.set("productId", filters.productId);
    if (filters.campaignId) params.set("campaignId", filters.campaignId);
    const qs = params.toString();
    return qs ? `/experiments?${qs}` : "/experiments";
  }, [filters.clientId, filters.productId, filters.campaignId]);

  return useQuery<Experiment[]>({
    queryKey: ["experiments", filters],
    queryFn: () => get(path),
    enabled,
  });
}
