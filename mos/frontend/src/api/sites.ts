import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useApiClient } from "@/api/client";

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
  createdAt: string;
  updatedAt: string;
}

interface SitePage {
  id: string;
  name: string;
  slug: string;
  pageType: string | null;
  templateId: string | null;
  ordering: number;
  isEntry: boolean;
  latestDraftVersionId: string | null;
  latestApprovedVersionId: string | null;
}

interface SiteDetail {
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
  entryPageId: string | null;
  pages: SitePage[];
  createdAt: string;
  updatedAt: string;
}

interface CreateSiteRequest {
  clientId: string;
  family: string;
  name: string;
  description?: string;
  productId: string;  // Required for publication
  designSystemId?: string;
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
