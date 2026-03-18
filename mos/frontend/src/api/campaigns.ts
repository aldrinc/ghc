import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type { Campaign, StrategyV2LaunchRecord } from "@/types/common";
import type { ExperimentSpec, Artifact } from "@/types/artifacts";
import type {
  CampaignDeliveryConfig,
  CampaignDeliveryValidationResponse,
  CampaignLaunchContextReadiness,
} from "@/types/delivery";

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

export function useCampaignDelivery(campaignId?: string) {
  const { get } = useApiClient();
  return useQuery<CampaignDeliveryConfig>({
    queryKey: ["campaigns", campaignId, "delivery"],
    queryFn: () => get(`/campaigns/${campaignId}/delivery`),
    enabled: Boolean(campaignId),
  });
}

export function useCampaignLaunchContextReadiness(campaignId?: string) {
  const { get } = useApiClient();
  return useQuery<CampaignLaunchContextReadiness>({
    queryKey: ["campaigns", campaignId, "launch-context-readiness"],
    queryFn: () => get(`/campaigns/${campaignId}/launch-context-readiness`),
    enabled: Boolean(campaignId),
  });
}

export function useUpdateCampaignDelivery(campaignId?: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: Omit<CampaignDeliveryConfig, "id" | "campaignId" | "clientId" | "validationStatus" | "validationError" | "validatedAt" | "createdAt" | "updatedAt">) => {
      if (!campaignId) throw new Error("Campaign ID is required");
      return request<CampaignDeliveryConfig>(`/campaigns/${campaignId}/delivery`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", campaignId, "delivery"] });
      toast.success("Delivery settings updated");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to update delivery settings";
      toast.error(message);
    },
  });
}

export function useValidateCampaignDelivery(campaignId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => {
      if (!campaignId) throw new Error("Campaign ID is required");
      return post<CampaignDeliveryValidationResponse>(`/campaigns/${campaignId}/delivery/validate`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", campaignId, "delivery"] });
      toast.success("Delivery validation complete");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to validate delivery settings";
      toast.error(message);
    },
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
