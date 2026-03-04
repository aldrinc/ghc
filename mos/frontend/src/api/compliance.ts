import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";

export const COMPLIANCE_RULESET_VERSION = "meta_tiktok_compliance_ruleset_v1";

export type ComplianceBusinessModel =
  | "ecommerce"
  | "saas_subscription"
  | "digital_product"
  | "online_service"
  | "lead_generation";

export type CompliancePolicyPageKey =
  | "privacy_policy"
  | "terms_of_service"
  | "returns_refunds_policy"
  | "shipping_policy"
  | "contact_support"
  | "company_information"
  | "subscription_terms_and_cancellation";

export type ComplianceShopifyPolicySyncPayload = {
  shopDomain?: string;
  pageKeys?: CompliancePolicyPageKey[];
  includeStronglyRecommended?: boolean;
};

export type ComplianceShopifyPolicySyncPage = {
  pageKey: CompliancePolicyPageKey;
  title: string;
  handle: string;
  pageId: string;
  url: string;
  operation: "created" | "updated";
  profileUrlField: string;
};

export type ComplianceShopifyPolicySyncResponse = {
  rulesetVersion: string;
  shopDomain: string;
  pages: ComplianceShopifyPolicySyncPage[];
  updatedProfileUrls: Record<string, string>;
};

export type ClientComplianceProfile = {
  id: string;
  orgId: string;
  clientId: string;
  rulesetVersion: string;
  businessModels: ComplianceBusinessModel[];
  legalBusinessName?: string | null;
  operatingEntityName?: string | null;
  companyAddressText?: string | null;
  businessLicenseIdentifier?: string | null;
  supportEmail?: string | null;
  supportPhone?: string | null;
  supportHoursText?: string | null;
  responseTimeCommitment?: string | null;
  privacyPolicyUrl?: string | null;
  termsOfServiceUrl?: string | null;
  returnsRefundsPolicyUrl?: string | null;
  shippingPolicyUrl?: string | null;
  contactSupportUrl?: string | null;
  companyInformationUrl?: string | null;
  subscriptionTermsAndCancellationUrl?: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type ClientComplianceProfileUpsertPayload = {
  rulesetVersion: string;
  businessModels: ComplianceBusinessModel[];
  legalBusinessName?: string;
  operatingEntityName?: string;
  companyAddressText?: string;
  businessLicenseIdentifier?: string;
  supportEmail?: string;
  supportPhone?: string;
  supportHoursText?: string;
  responseTimeCommitment?: string;
  privacyPolicyUrl?: string;
  termsOfServiceUrl?: string;
  returnsRefundsPolicyUrl?: string;
  shippingPolicyUrl?: string;
  contactSupportUrl?: string;
  companyInformationUrl?: string;
  subscriptionTermsAndCancellationUrl?: string;
  metadata?: Record<string, unknown>;
};

export function useClientComplianceProfile(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ClientComplianceProfile | null>({
    queryKey: ["clients", "compliance-profile", clientId],
    queryFn: async () => {
      try {
        return await get<ClientComplianceProfile>(`/clients/${clientId}/compliance/profile`);
      } catch (error) {
        const apiError = error as ApiError;
        if (apiError.status === 404) return null;
        throw error;
      }
    },
    enabled: Boolean(clientId),
  });
}

export function useUpsertClientComplianceProfile(clientId?: string) {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ClientComplianceProfileUpsertPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      return request<ClientComplianceProfile>(`/clients/${clientId}/compliance/profile`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      toast.success("Compliance profile saved");
      queryClient.invalidateQueries({ queryKey: ["clients", "compliance-profile", clientId] });
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to save compliance profile";
      toast.error(message);
    },
  });
}

export function useSyncComplianceShopifyPolicyPages(clientId?: string) {
  const { post } = useApiClient();

  return useMutation({
    mutationFn: (payload?: ComplianceShopifyPolicySyncPayload) => {
      if (!clientId) throw new Error("Client ID is required.");
      return post<ComplianceShopifyPolicySyncResponse>(
        `/clients/${clientId}/compliance/shopify/policy-pages/sync`,
        payload || {},
      );
    },
    onSuccess: (response) => {
      const count = response.pages.length;
      const suffix = count === 1 ? "" : "s";
      toast.success(`Synced ${count} policy page${suffix} to ${response.shopDomain}`);
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to sync compliance policy pages";
      toast.error(message);
    },
  });
}
