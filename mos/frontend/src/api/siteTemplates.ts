import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient } from "@/api/client";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { SiteThemeBindingMode } from "@/api/sites";

export interface SiteTemplate {
  id: string;
  name: string;
  description: string | null;
  siteType: string;
  siteFamily: string;
  commerceProvider: string | null;
  themeRequirement?: "optional" | "required" | null;
  scope: "system" | "workspace" | "org";
  status: "active" | "draft" | "archived";
  previewImageAssetId: string | null;
  pageCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface SiteTemplatePage {
  id: string;
  siteTemplateId: string;
  name: string;
  slug: string;
  pageType: string;
  pageRole: string | null;
  ordering: number;
  templateSourceId: string | null;
}

export interface SiteTemplateDetail extends SiteTemplate {
  pages: SiteTemplatePage[];
  links: {
    id: string;
    sourcePageId: string;
    targetPageId: string;
    linkType: string;
  }[];
}

export interface CreateSiteTemplateRequest {
  name: string;
  description?: string;
  siteType: string;
  siteFamily: string;
  commerceProvider?: string;
  scope?: "system" | "workspace" | "org";
}

export interface InstantiateSiteTemplateRequest {
  clientId: string;
  name: string;
  description?: string;
  productId?: string;
  themeBindingMode?: SiteThemeBindingMode;
  designSystemId?: string;
}

// Get all site templates (system + workspace scoped)
export function useSiteTemplates() {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SiteTemplate[]>({
    queryKey: ["site-templates", workspace?.id],
    queryFn: () => get<SiteTemplate[]>(`/site-templates?clientId=${workspace!.id}`),
    enabled: !!workspace?.id,
  });
}

// Get a single site template detail
export function useSiteTemplate(templateId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SiteTemplateDetail>({
    queryKey: ["site-templates", templateId],
    queryFn: () => get<SiteTemplateDetail>(`/site-templates/${templateId}?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!templateId,
  });
}

// Create a new site template (from existing site or scratch)
export function useCreateSiteTemplate() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: CreateSiteTemplateRequest) =>
      post<SiteTemplate>(`/site-templates?clientId=${workspace!.id}`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["site-templates", workspace?.id] });
    },
  });
}

// Instantiate a site template into a new site
export function useInstantiateSiteTemplate(templateId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: InstantiateSiteTemplateRequest) =>
      post<{ siteId: string }>(`/site-templates/${templateId}/instantiate?clientId=${workspace!.id}`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites", workspace?.id] });
    },
  });
}

// Create a site template from an existing site
export function useCreateSiteTemplateFromSite() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: ({ siteId, name, description }: { siteId: string; name: string; description?: string }) =>
      post<SiteTemplate>(`/sites/${siteId}/create-template?clientId=${workspace!.id}`, { name, description }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["site-templates", workspace?.id] });
    },
  });
}
