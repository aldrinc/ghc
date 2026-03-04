import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type { Campaign, StrategyV2LaunchRecord } from "@/types/common";
import type { ExperimentSpec, Artifact } from "@/types/artifacts";

export function useCampaign(campaignId?: string) {
  const { get } = useApiClient();
  return useQuery<Campaign>({
    queryKey: ["campaigns", campaignId],
    queryFn: () => get(`/campaigns/${campaignId}`),
    enabled: Boolean(campaignId),
  });
}

export function useCampaignStrategyV2Launches(campaignId?: string) {
  const { get } = useApiClient();
  return useQuery<StrategyV2LaunchRecord[]>({
    queryKey: ["campaigns", campaignId, "strategy-v2-launches"],
    queryFn: () => get(`/campaigns/${campaignId}/strategy-v2-launches`),
    enabled: Boolean(campaignId),
  });
}

export function useUpdateExperimentSpecs(campaignId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { experimentSpecs: ExperimentSpec[] }) => {
      if (!campaignId) throw new Error("Campaign ID is required");
      return post<Artifact>(`/campaigns/${campaignId}/experiment-specs`, payload);
    },
    onSuccess: () => {
      toast.success("Angle specs updated");
      queryClient.invalidateQueries({ queryKey: ["artifacts"] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update angle specs";
      toast.error(message);
    },
  });
}
