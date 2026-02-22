import { useMutation } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";

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
