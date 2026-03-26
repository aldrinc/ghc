import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useApiClient } from "@/api/client";
import type { Data } from "@measured/puck";
import type { MedusaRuntimeConfig } from "@/lib/medusa";

interface SiteFamilySummary {
  family: string;
  name: string;
  description: string;
  siteType: string;
  commerceProvider: string;
  pageCount: number;
}

interface SitePageBlueprint {
  pageType: string;
  templateId: string;
  name: string;
  slug: string;
  description: string | null;
  ordering: number;
  isEntry: boolean;
}

interface SiteFamilyDetail {
  family: string;
  name: string;
  description: string;
  siteType: string;
  commerceProvider: string;
  pageBlueprints: SitePageBlueprint[];
  provenanceNotes: string[];
}

interface SiteSummary {
  id: string;
  clientId: string;
  name: string;
  description: string | null;
  status: string;
  siteType: string | null;
  siteFamily: string | null;
  commerceProvider: string | null;
  productId?: string | null;
  designSystemId?: string | null;
  routeSlug?: string | null;
  primaryDomain?: string | null;
  templateId?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SitePage {
  id: string;
  name: string;
  slug: string;
  pageType: string | null;
  templateId: string | null;
  ordering: number;
  isEntry: boolean;
  designSystemId?: string | null;
  status?: string | null;
  latestDraftVersionId: string | null;
  latestApprovedVersionId: string | null;
}

interface SitePageVersion {
  id: string;
  status: "draft" | "approved" | "published";
  puckData: Data | null;
  createdAt: string;
  sourceType?: string | null;
  sourceId?: string | null;
}

export interface SiteDetail {
  id: string;
  clientId: string;
  name: string;
  description: string | null;
  status: string;
  experienceKind: string | null;
  siteType: string | null;
  siteFamily: string | null;
  commerceProvider: string | null;
  productId?: string | null;
  designSystemId?: string | null;
  entryPageId: string | null;
  routeSlug?: string | null;
  primaryDomain?: string | null;
  templateId?: string | null;
  pages: SitePage[];
  createdAt: string;
  updatedAt: string;
}

export interface SitePageDetail {
  site: {
    id: string;
    name: string;
    routeSlug: string | null;
    siteFamily: string | null;
    siteType: string | null;
    commerceProvider: string | null;
    productId: string | null;
    designSystemId: string | null;
  };
  page: {
    id: string;
    siteId: string;
    name: string;
    slug: string;
    pageType: string | null;
    templateId: string | null;
    ordering: number;
    designSystemId: string | null;
  };
  latestDraft: SitePageVersion | null;
  latestApproved: SitePageVersion | null;
  designSystemTokens: Record<string, unknown> | null;
}

interface CreateSiteRequest {
  clientId: string;
  family: string;
  name: string;
  description?: string;
  productId?: string;  // Optional - sites can exist without a single product
  designSystemId?: string;
}

interface UpdateSitePageRequest {
  name?: string;
  slug?: string;
  designSystemId?: string | null;
}

interface CreateSitePageVersionRequest {
  puckData: Data;
  status?: "draft" | "approved";
}

export interface SiteMedusaConfigResponse {
  siteFamily: string | null;
  commerceProvider: string | null;
  medusaConfig: (Pick<MedusaRuntimeConfig, "publishableKey"> & {
    baseUrl?: string | null;
    available: boolean;
  }) | null;
}

export function useSiteFamilies() {
  const { get } = useApiClient();
  return useQuery({
    queryKey: ["sites", "families"],
    queryFn: () => get<SiteFamilySummary[]>("/sites/families"),
  });
}

export function useSiteFamily(family: string | null) {
  const { get } = useApiClient();
  return useQuery({
    queryKey: ["sites", "families", family],
    queryFn: () => get<SiteFamilyDetail>(`/sites/families/${family}`),
    enabled: !!family,
  });
}

export function useSites() {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery({
    queryKey: ["sites", workspace?.id],
    queryFn: () => get<SiteSummary[]>(`/sites?clientId=${workspace!.id}`),
    enabled: !!workspace?.id,
  });
}

export function useSite(siteId: string | null) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery({
    queryKey: ["sites", workspace?.id ?? null, siteId],
    queryFn: () => get<SiteDetail>(`/sites/${siteId}?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!siteId,
  });
}

export function useCreateSite() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: CreateSiteRequest) => post<SiteDetail>("/sites", request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", workspace?.id] });
    },
  });
}

// Site Page Editor APIs
export function useSitePage(siteId: string | null | undefined, pageId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SitePageDetail>({
    queryKey: ["sites", siteId, "pages", pageId],
    queryFn: () => get<SitePageDetail>(`/sites/${siteId}/pages/${pageId}?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!siteId && !!pageId,
  });
}

export function useUpdateSitePage(siteId: string | null | undefined, pageId: string | null | undefined) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (payload: UpdateSitePageRequest) =>
      request<SitePage>(`/sites/${siteId}/pages/${pageId}?clientId=${workspace!.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "pages", pageId] });
      queryClient.invalidateQueries({ queryKey: ["sites", workspace?.id ?? null, siteId] });
      queryClient.invalidateQueries({ queryKey: ["sites", workspace?.id] });
    },
  });
}

export function useCreateSitePageVersion(siteId: string | null | undefined, pageId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: CreateSitePageVersionRequest) =>
      post<SitePageVersion>(`/sites/${siteId}/pages/${pageId}/versions?clientId=${workspace!.id}`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "pages", pageId] });
      queryClient.invalidateQueries({ queryKey: ["sites", workspace?.id ?? null, siteId] });
    },
  });
}

export function useSiteMedusaConfig(siteId: string | null | undefined) {
  const { get } = useApiClient();
  return useQuery<SiteMedusaConfigResponse>({
    queryKey: ["sites", siteId, "medusa-config"],
    queryFn: () => get<SiteMedusaConfigResponse>(`/sites/${siteId}/medusa-config`),
    enabled: !!siteId,
  });
}
