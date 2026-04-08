import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type { Campaign, CampaignSwipeDefault, StrategyV2LaunchRecord } from "@/types/common";
import type { ExperimentSpec, Artifact } from "@/types/artifacts";
import type {
  CampaignDeliveryConfig,
  CampaignDeliveryValidationResponse,
  CampaignLaunchContextReadiness,
} from "@/types/delivery";

export type CampaignSkillsCreativeContextMaterializeResponse = {
  campaignId: string;
  provider: "skills";
  creativeContextArtifactId: string;
  artifactIds: Record<string, string>;
  sourceArtifactIds: Record<string, string | null>;
  strategyBundleId: string;
  strategyBundleType: string;
  uploadedDocKeys: string[];
  refreshed: boolean;
  staleArtifactId?: string | null;
  checkedAt: string;
};

export type CampaignCreativeContextAngleSummary = {
  angleId: string;
  angleName: string;
  description?: string | null;
  evidence: string[];
};

export type CampaignCreativeContextAnglesResponse = {
  campaignId: string;
  provider: "strategy_v2" | "manual" | "skills";
  selectedAngleId?: string | null;
  angles: CampaignCreativeContextAngleSummary[];
};
export const CAMPAIGN_SWIPE_COLLECTION_QUERY_KEY = (campaignId: string) =>
  ["campaigns", campaignId, "swipe-collection"] as const;

function getMutationErrorMessage(err: ApiError | Error, fallback: string): string {
  if ("message" in err && typeof err.message === "string") return err.message;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function useCampaign(campaignId?: string) {
  const { get } = useApiClient();
  return useQuery<Campaign>({
    queryKey: ["campaigns", campaignId],
    queryFn: () => get(`/campaigns/${campaignId}`),
    enabled: Boolean(campaignId),
  });
}

export function useCampaignsForProduct(clientId?: string | null, productId?: string | null) {
  const { get } = useApiClient();
  return useQuery<Campaign[]>({
    queryKey: ["campaigns", "by-product", clientId, productId],
    queryFn: () => get(`/campaigns?client_id=${clientId}&product_id=${productId}`),
    enabled: Boolean(clientId && productId),
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

export function useMaterializeCampaignCreativeContext(campaignId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => {
      if (!campaignId) throw new Error("Campaign ID is required");
      return post<CampaignSkillsCreativeContextMaterializeResponse>(
        `/campaigns/${campaignId}/creative-context/materialize`,
      );
    },
    onSuccess: () => {
      if (campaignId) {
        queryClient.invalidateQueries({ queryKey: ["campaigns", campaignId, "launch-context-readiness"] });
      }
      toast.success("Campaign skills context materialized");
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to materialize campaign creative context"));
    },
  });
}

export function useCampaignCreativeContextAngles(campaignId?: string | null) {
  const { get } = useApiClient();
  return useQuery<CampaignCreativeContextAnglesResponse>({
    queryKey: ["campaigns", campaignId, "creative-context-angles"],
    queryFn: () => get(`/campaigns/${campaignId}/creative-context/angles`),
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
      toast.error(getMutationErrorMessage(err, "Failed to update delivery settings"));
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
      toast.error(getMutationErrorMessage(err, "Failed to validate delivery settings"));
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
      toast.error(getMutationErrorMessage(err, "Failed to update angle specs"));
    },
  });
}

export function useCampaignSwipeCollection(campaignId?: string) {
  const { get } = useApiClient();
  return useQuery<CampaignSwipeDefault>({
    queryKey: campaignId ? CAMPAIGN_SWIPE_COLLECTION_QUERY_KEY(campaignId) : ["campaigns", "swipe-collection"],
    queryFn: () => get(`/campaigns/${campaignId}/swipe-default`),
    enabled: Boolean(campaignId),
  });
}

export function useUpdateCampaignSwipeCollection(campaignId?: string) {
  const { put } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (swipeCollectionId: string | null) => {
      if (!campaignId) throw new Error("Campaign ID is required");
      return put<CampaignSwipeDefault>(`/campaigns/${campaignId}/swipe-default`, {
        swipeCollectionId: swipeCollectionId,
      });
    },
    onSuccess: () => {
      toast.success("Default swipe collection updated");
      if (campaignId) {
        queryClient.invalidateQueries({ queryKey: ["campaigns", campaignId] });
        queryClient.invalidateQueries({ queryKey: CAMPAIGN_SWIPE_COLLECTION_QUERY_KEY(campaignId) });
      }
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to update default swipe collection"));
    },
  });
}
