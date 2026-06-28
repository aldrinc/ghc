import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type {
  AgentActionProposal,
  ContentExperiment,
  ContentExperimentInput,
  ContentGrowthProgram,
  ContentGrowthProgramInput,
  ContentVariant,
  ContentVariantInput,
  ConversionEventInput,
  ConversionSource,
  ConversionSourceInput,
  PostizHandoffProposal,
  PostizHandoffProposalInput,
  SocialProviderAsset,
} from "@/types/socialAgents";

function errorMessage(err: ApiError | Error, fallback: string) {
  return "message" in err ? err.message : fallback;
}

export function useSocialProviderAssets(clientId?: string, provider?: string) {
  const { get } = useApiClient();
  return useQuery<SocialProviderAsset[]>({
    queryKey: ["clients", "connected-social-assets", clientId, provider || "all"],
    queryFn: () => {
      const params = provider ? `?provider=${encodeURIComponent(provider)}` : "";
      return get(`/clients/${clientId}/connected-social/provider-assets${params}`);
    },
    enabled: Boolean(clientId),
  });
}

export function useAgentActionProposals(clientId?: string, status?: string) {
  const { get } = useApiClient();
  return useQuery<AgentActionProposal[]>({
    queryKey: ["clients", "connected-social-action-proposals", clientId, status || "all"],
    queryFn: () => {
      const params = status ? `?status=${encodeURIComponent(status)}` : "";
      return get(`/clients/${clientId}/connected-social/action-proposals${params}`);
    },
    enabled: Boolean(clientId),
  });
}

export function useApproveAgentActionProposal(clientId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ proposalId, notes }: { proposalId: string; notes?: string | null }) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<AgentActionProposal>(
        `/clients/${clientId}/connected-social/action-proposals/${proposalId}/approve`,
        { notes: notes || null },
      );
    },
    onSuccess: () => {
      toast.success("Action proposal approved");
      queryClient.invalidateQueries({ queryKey: ["clients", "connected-social-action-proposals", clientId] });
    },
    onError: (err: ApiError | Error) => toast.error(errorMessage(err, "Failed to approve action proposal")),
  });
}

export function useGrowthPrograms(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ContentGrowthProgram[]>({
    queryKey: ["clients", "growth-programs", clientId],
    queryFn: () => get(`/clients/${clientId}/growth-programs`),
    enabled: Boolean(clientId),
  });
}

export function useCreateGrowthProgram(clientId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ContentGrowthProgramInput) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<ContentGrowthProgram>(`/clients/${clientId}/growth-programs`, payload);
    },
    onSuccess: () => {
      toast.success("Growth program created");
      queryClient.invalidateQueries({ queryKey: ["clients", "growth-programs", clientId] });
    },
    onError: (err: ApiError | Error) => toast.error(errorMessage(err, "Failed to create growth program")),
  });
}

export function useConversionSources(clientId?: string, programId?: string) {
  const { get } = useApiClient();
  return useQuery<ConversionSource[]>({
    queryKey: ["clients", "growth-program-conversion-sources", clientId, programId],
    queryFn: () => get(`/clients/${clientId}/growth-programs/${programId}/conversion-sources`),
    enabled: Boolean(clientId && programId),
  });
}

export function useCreateConversionSource(clientId?: string, programId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConversionSourceInput) => {
      if (!clientId || !programId) throw new Error("Client ID and program ID are required.");
      return post<ConversionSource>(`/clients/${clientId}/growth-programs/${programId}/conversion-sources`, payload);
    },
    onSuccess: () => {
      toast.success("Conversion source created");
      queryClient.invalidateQueries({ queryKey: ["clients", "growth-program-conversion-sources", clientId, programId] });
      queryClient.invalidateQueries({ queryKey: ["clients", "growth-programs", clientId] });
    },
    onError: (err: ApiError | Error) => toast.error(errorMessage(err, "Failed to create conversion source")),
  });
}

export function useContentExperiments(clientId?: string, programId?: string) {
  const { get } = useApiClient();
  return useQuery<ContentExperiment[]>({
    queryKey: ["clients", "content-experiments", clientId, programId],
    queryFn: () => get(`/clients/${clientId}/growth-programs/${programId}/experiments`),
    enabled: Boolean(clientId && programId),
  });
}

export function useCreateContentExperiment(clientId?: string, programId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ContentExperimentInput) => {
      if (!clientId || !programId) throw new Error("Client ID and program ID are required.");
      return post<ContentExperiment>(`/clients/${clientId}/growth-programs/${programId}/experiments`, payload);
    },
    onSuccess: () => {
      toast.success("Experiment created");
      queryClient.invalidateQueries({ queryKey: ["clients", "content-experiments", clientId, programId] });
    },
    onError: (err: ApiError | Error) => toast.error(errorMessage(err, "Failed to create experiment")),
  });
}

export function useContentVariants(clientId?: string, programId?: string) {
  const { get } = useApiClient();
  return useQuery<ContentVariant[]>({
    queryKey: ["clients", "content-variants", clientId, programId],
    queryFn: () => get(`/clients/${clientId}/growth-programs/${programId}/variants`),
    enabled: Boolean(clientId && programId),
  });
}

export function useCreateContentVariant(clientId?: string, programId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ContentVariantInput) => {
      if (!clientId || !programId) throw new Error("Client ID and program ID are required.");
      return post<ContentVariant>(`/clients/${clientId}/growth-programs/${programId}/variants`, payload);
    },
    onSuccess: () => {
      toast.success("Carousel variant created");
      queryClient.invalidateQueries({ queryKey: ["clients", "content-variants", clientId, programId] });
    },
    onError: (err: ApiError | Error) => toast.error(errorMessage(err, "Failed to create carousel variant")),
  });
}

export function useApproveContentVariant(clientId?: string, programId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ variantId, notes }: { variantId: string; notes?: string | null }) => {
      if (!clientId || !programId) throw new Error("Client ID and program ID are required.");
      return post<ContentVariant>(
        `/clients/${clientId}/growth-programs/${programId}/variants/${variantId}/approve`,
        { notes: notes || null },
      );
    },
    onSuccess: () => {
      toast.success("Carousel variant approved");
      queryClient.invalidateQueries({ queryKey: ["clients", "content-variants", clientId, programId] });
    },
    onError: (err: ApiError | Error) => toast.error(errorMessage(err, "Failed to approve carousel variant")),
  });
}

export function useCreatePostizHandoffProposal(clientId?: string, programId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ variantId, payload }: { variantId: string; payload: PostizHandoffProposalInput }) => {
      if (!clientId || !programId) throw new Error("Client ID and program ID are required.");
      return post<PostizHandoffProposal>(
        `/clients/${clientId}/growth-programs/${programId}/variants/${variantId}/postiz-handoff-proposals`,
        payload,
      );
    },
    onSuccess: () => {
      toast.success("Postiz handoff proposal created");
      queryClient.invalidateQueries({ queryKey: ["clients", "connected-social-action-proposals", clientId] });
    },
    onError: (err: ApiError | Error) => toast.error(errorMessage(err, "Failed to create Postiz handoff proposal")),
  });
}

export function useCreateConversionEvent(clientId?: string, programId?: string) {
  const { post } = useApiClient();
  return useMutation({
    mutationFn: (payload: ConversionEventInput) => {
      if (!clientId || !programId) throw new Error("Client ID and program ID are required.");
      return post(`/clients/${clientId}/growth-programs/${programId}/conversion-events`, payload);
    },
    onSuccess: () => toast.success("Conversion event recorded"),
    onError: (err: ApiError | Error) => toast.error(errorMessage(err, "Failed to record conversion event")),
  });
}
