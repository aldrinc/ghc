import { useCallback } from "react";
import { useApiClient } from "./client";
import type {
  MetaAdAccountConnection,
  MetaAdAccountConnectionUpsertPayload,
  MetaAdSetSpec,
  MetaAdSetSpecUpdatePayload,
  MetaManagementPlan,
  MetaManagementPlanRequest,
  MetaPipelineAsset,
  MetaPublishPlanValidation,
  MetaPublishRun,
  MetaPublishRunRequest,
  MetaPublishSelection,
  MetaPublishSelectionMutation,
  MetaRemoteResponse,
  MetaRemoteImage,
  MetaRemoteVideo,
  MetaRemoteCreative,
  MetaRemoteCampaign,
  MetaRemoteAdSet,
  MetaRemoteAd,
  MetaWorkspaceAdConfig,
  MetaWorkspaceAdConfigCreatePayload,
} from "@/types/meta";

type PipelineFilters = {
  clientId?: string;
  productId?: string;
  campaignId?: string;
  experimentId?: string;
  assetKind?: string;
  statuses?: string[];
  metaConfigId?: string;
};

type RemoteFilters = {
  clientId?: string;
  metaConfigId?: string;
  adAccountId?: string;
  fields?: string;
  limit?: number;
  after?: string;
  fetchAll?: boolean;
};

export function useMetaApi() {
  const { get, request } = useApiClient();

  const listConnections = useCallback(() => get<MetaAdAccountConnection[]>("/meta/connections"), [get]);

  const createConnection = useCallback(
    (payload: MetaAdAccountConnectionUpsertPayload) =>
      request<MetaAdAccountConnection>("/meta/connections", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    [request],
  );

  const validateConnection = useCallback(
    (connectionId: string) =>
      request<MetaAdAccountConnection>(`/meta/connections/${connectionId}/validate`, {
        method: "POST",
      }),
    [request],
  );

  const getActiveConfig = useCallback(
    (clientId: string) => get<MetaWorkspaceAdConfig>(`/meta/clients/${clientId}/active-config`),
    [get],
  );

  const getConfig = useCallback(
    (clientId: string, metaConfigId?: string) => {
      const params = new URLSearchParams();
      params.set("clientId", clientId);
      if (metaConfigId) params.set("metaConfigId", metaConfigId);
      return get<MetaWorkspaceAdConfig>(`/meta/config?${params.toString()}`);
    },
    [get],
  );

  const listWorkspaceConfigs = useCallback(
    (clientId: string) => get<MetaWorkspaceAdConfig[]>(`/meta/clients/${clientId}/configs`),
    [get],
  );

  const createWorkspaceConfig = useCallback(
    (clientId: string, payload: MetaWorkspaceAdConfigCreatePayload) =>
      request<MetaWorkspaceAdConfig>(`/meta/clients/${clientId}/configs`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    [request],
  );

  const selectWorkspaceConfig = useCallback(
    (clientId: string, configId: string) =>
      request<MetaWorkspaceAdConfig>(`/meta/clients/${clientId}/configs/${configId}/select`, {
        method: "POST",
      }),
    [request],
  );

  const validateWorkspaceConfig = useCallback(
    (clientId: string, configId: string) =>
      request<MetaWorkspaceAdConfig>(`/meta/clients/${clientId}/configs/${configId}/validate`, {
        method: "POST",
      }),
    [request],
  );

  const listPipelineAssets = useCallback(
    (filters: PipelineFilters = {}) => {
      const params = new URLSearchParams();
      if (filters.clientId) params.set("clientId", filters.clientId);
      if (filters.productId) params.set("productId", filters.productId);
      if (filters.campaignId) params.set("campaignId", filters.campaignId);
      if (filters.experimentId) params.set("experimentId", filters.experimentId);
      if (filters.assetKind) params.set("assetKind", filters.assetKind);
      if (filters.metaConfigId) params.set("metaConfigId", filters.metaConfigId);
      if (filters.statuses?.length) {
        filters.statuses.forEach((status) => params.append("statuses", status));
      }
      const qs = params.toString();
      return get<MetaPipelineAsset[]>(qs ? `/meta/pipeline/assets?${qs}` : "/meta/pipeline/assets");
    },
    [get],
  );

  const buildRemotePath = (base: string, filters: RemoteFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.clientId) params.set("clientId", filters.clientId);
    if (filters.metaConfigId) params.set("metaConfigId", filters.metaConfigId);
    if (filters.adAccountId) params.set("adAccountId", filters.adAccountId);
    if (filters.fields) params.set("fields", filters.fields);
    if (typeof filters.limit === "number") params.set("limit", filters.limit.toString());
    if (filters.after) params.set("after", filters.after);
    if (filters.fetchAll) params.set("fetchAll", "true");
    const qs = params.toString();
    return qs ? `${base}?${qs}` : base;
  };

  const listRemoteImages = useCallback(
    (filters?: RemoteFilters) => get<MetaRemoteResponse<MetaRemoteImage>>(buildRemotePath("/meta/remote/adimages", filters)),
    [get],
  );

  const listRemoteVideos = useCallback(
    (filters?: RemoteFilters) => get<MetaRemoteResponse<MetaRemoteVideo>>(buildRemotePath("/meta/remote/advideos", filters)),
    [get],
  );

  const listRemoteCreatives = useCallback(
    (filters?: RemoteFilters) =>
      get<MetaRemoteResponse<MetaRemoteCreative>>(buildRemotePath("/meta/remote/adcreatives", filters)),
    [get],
  );

  const listRemoteCampaigns = useCallback(
    (filters?: RemoteFilters) =>
      get<MetaRemoteResponse<MetaRemoteCampaign>>(buildRemotePath("/meta/remote/campaigns", filters)),
    [get],
  );

  const listRemoteAdSets = useCallback(
    (filters?: RemoteFilters) =>
      get<MetaRemoteResponse<MetaRemoteAdSet>>(buildRemotePath("/meta/remote/adsets", filters)),
    [get],
  );

  const listRemoteAds = useCallback(
    (filters?: RemoteFilters) => get<MetaRemoteResponse<MetaRemoteAd>>(buildRemotePath("/meta/remote/ads", filters)),
    [get],
  );

  const listPublishSelections = useCallback(
    (campaignId: string, generationKey: string) => {
      const params = new URLSearchParams({ generationKey });
      return get<MetaPublishSelection[]>(`/meta/campaigns/${campaignId}/publish-selections?${params.toString()}`);
    },
    [get],
  );

  const savePublishSelections = useCallback(
    (campaignId: string, payload: { generationKey: string; decisions: MetaPublishSelectionMutation[] }) =>
      request<MetaPublishSelection[]>(`/meta/campaigns/${campaignId}/publish-selections`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    [request],
  );

  const updateAdSetSpec = useCallback(
    (adsetSpecId: string, payload: MetaAdSetSpecUpdatePayload) =>
      request<MetaAdSetSpec>(`/meta/specs/adsets/${adsetSpecId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    [request],
  );

  const validatePublishPlan = useCallback(
    (campaignId: string, payload: MetaPublishRunRequest) =>
      request<MetaPublishPlanValidation>(`/meta/campaigns/${campaignId}/publish-plan/validate`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    [request],
  );

  const listPublishRuns = useCallback(
    (campaignId: string) => get<MetaPublishRun[]>(`/meta/campaigns/${campaignId}/publish-runs`),
    [get],
  );

  const createPublishRun = useCallback(
    (campaignId: string, payload: MetaPublishRunRequest) =>
      request<MetaPublishRun>(`/meta/campaigns/${campaignId}/publish-runs`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    [request],
  );

  const planManagement = useCallback(
    (payload: MetaManagementPlanRequest) =>
      request<MetaManagementPlan>("/meta/management/plan", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    [request],
  );

  return {
    listConnections,
    createConnection,
    validateConnection,
    getActiveConfig,
    getConfig,
    listWorkspaceConfigs,
    createWorkspaceConfig,
    selectWorkspaceConfig,
    validateWorkspaceConfig,
    listPipelineAssets,
    listRemoteImages,
    listRemoteVideos,
    listRemoteCreatives,
    listRemoteCampaigns,
    listRemoteAdSets,
    listRemoteAds,
    listPublishSelections,
    savePublishSelections,
    updateAdSetSpec,
    validatePublishPlan,
    listPublishRuns,
    createPublishRun,
    planManagement,
  };
}
