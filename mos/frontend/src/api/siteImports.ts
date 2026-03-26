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
  savedSiteId?: string | null;
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
  description?: string;
  family?: string;
  pageType?: string;
  acceptedSectionIds?: string[];
  reviewNotes?: string;
}

export interface ApplySiteImportResponse {
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
    mutationFn: async (request: ApplySiteImportRequest) => {
      if (!importId) throw new Error("Import ID is required.");
      if (!workspace?.id) throw new Error("Workspace is required.");

      const basePath = `/site-imports/${importId}`;
      const clientQuery = `?clientId=${workspace.id}`;

      if (request.action === "create-site") {
        if (!request.name?.trim()) throw new Error("Site name is required.");
        const result = await post<{ siteId: string }>(`${basePath}/create-site${clientQuery}`, {
          siteName: request.name.trim(),
          description: request.description,
        });
        return { siteId: result.siteId };
      }

      if (request.action === "add-pages") {
        if (!request.targetSiteId) throw new Error("Target site is required.");
        const result = await post<{ siteId: string }>(`${basePath}/add-pages${clientQuery}`, {
          siteId: request.targetSiteId,
        });
        return { siteId: result.siteId };
      }

      if (request.action === "create-site-template") {
        if (!request.name?.trim() || !request.family) {
          throw new Error("Template name and family are required.");
        }
        const result = await post<{ siteTemplateId: string }>(
          `${basePath}/create-site-template${clientQuery}`,
          {
            name: request.name.trim(),
            family: request.family,
            description: request.description,
          },
        );
        return { siteTemplateId: result.siteTemplateId };
      }

      if (!request.name?.trim() || !request.family || !request.pageType) {
        throw new Error("Template name, family, and page type are required.");
      }
      const result = await post<{ variantId: string }>(
        `${basePath}/create-page-template${clientQuery}`,
        {
          name: request.name.trim(),
          family: request.family,
          pageType: request.pageType,
          acceptedSectionIds: request.acceptedSectionIds || [],
          reviewNotes: request.reviewNotes,
        },
      );
      return { pageTemplateId: result.variantId };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["site-imports", importId] });
      queryClient.invalidateQueries({ queryKey: ["site-imports", workspace?.id] });
      queryClient.invalidateQueries({ queryKey: ["sites", workspace?.id] });
      queryClient.invalidateQueries({ queryKey: ["site-templates", workspace?.id] });
    },
  });
}
