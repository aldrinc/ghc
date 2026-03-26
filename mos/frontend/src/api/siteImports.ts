import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient } from "@/api/client";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export interface SiteImport {
  id: string;
  clientId: string;
  sourceUrl: string;
  sourceHostname: string | null;
  status: "queued" | "capturing" | "generating" | "adapting" | "completed" | "failed";
  title: string | null;
  suggestedTemplateFamily: string | null;
  detectedPageCount: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface SiteImportDetail extends SiteImport {
  sections: {
    id: string;
    sectionType: string;
    normalizedHtml: string | null;
    normalizedReact: string | null;
    screenshotUrl: string | null;
    ordering: number;
  }[];
  applications: SiteImportApplication[];
}

export interface SiteImportApplication {
  id: string;
  siteImportId: string;
  targetType: "site" | "site_template" | "page_template" | "site_pages";
  targetId: string;
  action: "create-site" | "add-pages" | "create-site-template" | "create-page-template";
  siteId: string | null;
  sitePageId: string | null;
  siteTemplateId: string | null;
  pageTemplateId: string | null;
  createdAt: string;
}

export interface CreateSiteImportRequest {
  sourceUrl: string;
  title?: string;
}

export interface ApplySiteImportRequest {
  action: "create-site" | "add-pages" | "create-site-template" | "create-page-template";
  siteTemplateId?: string;
  targetSiteId?: string;
  name?: string;
}

export interface ApplySiteImportResponse {
  applicationId: string;
  siteId?: string;
  siteTemplateId?: string;
  pageTemplateId?: string;
}

// Get all site imports for workspace
export function useSiteImports() {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SiteImport[]>({
    queryKey: ["site-imports", workspace?.id],
    queryFn: () => get<SiteImport[]>(`/site-imports?clientId=${workspace!.id}`),
    enabled: !!workspace?.id,
  });
}

// Get a single site import detail
export function useSiteImport(importId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  return useQuery<SiteImportDetail>({
    queryKey: ["site-imports", importId],
    queryFn: () => get<SiteImportDetail>(`/site-imports/${importId}?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!importId,
  });
}

// Create a new site import
export function useCreateSiteImport() {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: CreateSiteImportRequest) =>
      post<SiteImport>(`/site-imports?clientId=${workspace!.id}`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["site-imports", workspace?.id] });
    },
  });
}

// Apply a site import (create site, add pages, create template, etc.)
export function useApplySiteImport(importId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: ApplySiteImportRequest) =>
      post<ApplySiteImportResponse>(`/site-imports/${importId}/apply?clientId=${workspace!.id}`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["site-imports", importId] });
      queryClient.invalidateQueries({ queryKey: ["sites", workspace?.id] });
      queryClient.invalidateQueries({ queryKey: ["site-templates", workspace?.id] });
    },
  });
}
