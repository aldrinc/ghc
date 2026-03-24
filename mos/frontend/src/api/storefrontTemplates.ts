import { useMutation, useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/api/client";
import type {
  ApproveForPublishRequest,
  ApproveForPublishResponse,
  ConvertImportRequest,
  CreateDraftFromTemplateRequest,
  CreateDraftFromTemplateResponse,
  CreateSiteImportRequest,
  GenerateVariantsRequest,
  GenerateVariantsResponse,
  GeneratedVariantSummary,
  GovernanceReport,
  MutationPresetPreview,
  MutationPresetSummary,
  SiteImportDetail,
  SiteImportSnapshot,
  SiteImportSummary,
  StorefrontBindingPreview,
  StorefrontTemplateDetail,
  StorefrontTemplateSummary,
  TemplateVariantDetail,
  TemplateVariantDetailExtended,
  TemplateVariantSummary,
} from "@/types/storefrontTemplates";

export function useStorefrontTemplates() {
  const { get } = useApiClient();
  return useQuery<StorefrontTemplateSummary[]>({
    queryKey: ["storefront", "templates"],
    queryFn: () => get("/storefront/templates"),
  });
}

export function useStorefrontTemplate(templateId?: string) {
  const { get } = useApiClient();
  return useQuery<StorefrontTemplateDetail>({
    queryKey: ["storefront", "templates", templateId],
    queryFn: () => get(`/storefront/templates/${templateId}`),
    enabled: Boolean(templateId),
  });
}

export function useStorefrontBindingPreview({
  templateId,
  clientId,
  productId,
  variantId,
}: {
  templateId?: string;
  clientId?: string;
  productId?: string;
  variantId?: string;
}) {
  const { get } = useApiClient();
  return useQuery<StorefrontBindingPreview>({
    queryKey: ["storefront", "binding-preview", templateId, clientId, productId, variantId],
    queryFn: () => {
      const query = new URLSearchParams();
      query.set("clientId", clientId || "");
      if (productId) query.set("productId", productId);
      if (variantId) query.set("variantId", variantId);
      return get(`/storefront/templates/${templateId}/binding-preview?${query.toString()}`);
    },
    enabled: Boolean(templateId && clientId),
  });
}

// Site Import API
export function useSiteImports(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<SiteImportSummary[]>({
    queryKey: ["storefront", "imports", clientId],
    queryFn: () => get(`/storefront/templates/imports?clientId=${clientId}`),
    enabled: Boolean(clientId),
  });
}

export function useSiteImportDetail(
  importId?: string,
  clientId?: string,
  targetFamily?: string,
  targetPageType?: string,
  acceptedSectionIds?: string[]
) {
  const { get } = useApiClient();
  return useQuery<SiteImportDetail>({
    queryKey: ["storefront", "imports", importId, clientId, targetFamily, targetPageType, acceptedSectionIds],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("clientId", clientId || "");
      if (targetFamily) params.set("targetFamily", targetFamily);
      if (targetPageType) params.set("targetPageType", targetPageType);
      if (acceptedSectionIds && acceptedSectionIds.length > 0) {
        params.set("acceptedSectionIds", acceptedSectionIds.join(","));
      }
      return get(`/storefront/templates/imports/${importId}?${params.toString()}`);
    },
    enabled: Boolean(importId && clientId),
  });
}

export function useSiteImportSnapshot(importId?: string, clientId?: string) {
  const { get } = useApiClient();
  return useQuery<SiteImportSnapshot>({
    queryKey: ["storefront", "imports", importId, "snapshot", clientId],
    queryFn: () => get(`/storefront/templates/imports/${importId}/snapshot?clientId=${clientId}`),
    enabled: Boolean(importId && clientId),
  });
}

export function useCreateSiteImport() {
  const { post } = useApiClient();
  return useMutation({
    mutationFn: (request: CreateSiteImportRequest & { clientId: string }) => {
      return post<SiteImportSummary>(`/storefront/templates/imports?clientId=${request.clientId}`, request);
    },
  });
}

export function useConvertImport() {
  const { post } = useApiClient();
  return useMutation({
    mutationFn: (request: ConvertImportRequest & { importId: string; clientId: string }) => {
      const { importId, clientId, ...body } = request;
      return post<TemplateVariantDetail>(
        `/storefront/templates/imports/${importId}/convert?clientId=${clientId}`,
        body
      );
    },
  });
}

export function useTemplateVariants(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<TemplateVariantSummary[]>({
    queryKey: ["storefront", "variants", clientId],
    queryFn: () => get(`/storefront/templates/variants?clientId=${clientId}`),
    enabled: Boolean(clientId),
  });
}

export function useTemplateVariantDetail(variantId?: string, clientId?: string) {
  const { get } = useApiClient();
  return useQuery<TemplateVariantDetailExtended>({
    queryKey: ["storefront", "variants", variantId, clientId],
    queryFn: () => get(`/storefront/templates/variants/${variantId}?clientId=${clientId}`),
    enabled: Boolean(variantId && clientId),
  });
}

export function useMutationPresets(family?: string) {
  const { get } = useApiClient();
  return useQuery<MutationPresetSummary[]>({
    queryKey: ["storefront", "presets", family],
    queryFn: () => {
      const params = new URLSearchParams();
      if (family) params.set("family", family);
      const query = params.toString() ? `?${params.toString()}` : "";
      return get(`/storefront/templates/presets${query}`);
    },
  });
}

export function useVariantPresets(variantId?: string, clientId?: string) {
  const { get } = useApiClient();
  return useQuery<MutationPresetPreview[]>({
    queryKey: ["storefront", "variants", variantId, "presets", clientId],
    queryFn: () => get(`/storefront/templates/variants/${variantId}/presets?clientId=${clientId}`),
    enabled: Boolean(variantId && clientId),
  });
}

export function useGenerateVariants() {
  const { post } = useApiClient();
  return useMutation({
    mutationFn: (request: GenerateVariantsRequest & { variantId: string; clientId: string }) => {
      const { variantId, clientId, ...body } = request;
      return post<GenerateVariantsResponse>(
        `/storefront/templates/variants/${variantId}/generate?clientId=${clientId}`,
        body
      );
    },
  });
}

// Governance API (Phase 5)

export function useVariantGovernance(variantId?: string, clientId?: string) {
  const { get } = useApiClient();
  return useQuery<GovernanceReport>({
    queryKey: ["storefront", "variants", variantId, "governance", clientId],
    queryFn: () => get(`/storefront/templates/variants/${variantId}/governance?clientId=${clientId}`),
    enabled: Boolean(variantId && clientId),
  });
}

export function useApproveForPublish() {
  const { post } = useApiClient();
  return useMutation({
    mutationFn: (request: ApproveForPublishRequest & { variantId: string; clientId: string }) => {
      const { variantId, clientId, ...body } = request;
      return post<ApproveForPublishResponse>(
        `/storefront/templates/variants/${variantId}/approve?clientId=${clientId}`,
        body
      );
    },
  });
}

// Create Draft from Template API

export function useCreateDraftFromTemplate() {
  const { post } = useApiClient();
  return useMutation({
    mutationFn: (request: CreateDraftFromTemplateRequest & { templateId: string; clientId: string }) => {
      const { templateId, clientId, ...body } = request;
      return post<CreateDraftFromTemplateResponse>(
        `/storefront/templates/${templateId}/drafts?clientId=${clientId}`,
        body
      );
    },
  });
}
