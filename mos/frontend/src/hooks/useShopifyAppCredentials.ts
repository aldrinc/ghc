import { useEffect, useMemo, useState } from "react";
import {
  useClientShopifyAppCredentials,
  useUpdateClientShopifyAppCredentials,
} from "@/api/clients";
import { toast } from "@/components/ui/toast";

export function useShopifyAppCredentials(workspaceId: string | undefined) {
  const {
    data: shopifyAppCredentials,
    isLoading: isLoadingShopifyAppCredentials,
    refetch: refetchShopifyAppCredentials,
  } = useClientShopifyAppCredentials(workspaceId);
  const updateShopifyAppCredentials = useUpdateClientShopifyAppCredentials(workspaceId || "");

  const [shopifyAppApiKeyDraft, setShopifyAppApiKeyDraft] = useState("");
  const [shopifyAppApiSecretDraft, setShopifyAppApiSecretDraft] = useState("");

  useEffect(() => {
    const nextApiKey =
      typeof shopifyAppCredentials?.apiKey === "string" ? shopifyAppCredentials.apiKey.trim() : "";
    setShopifyAppApiKeyDraft(nextApiKey);
    setShopifyAppApiSecretDraft("");
  }, [shopifyAppCredentials?.apiKey, workspaceId]);

  const hasConfiguredShopifyAppCredentials = Boolean(shopifyAppCredentials?.isConfigured);
  const shopifyAppCredentialsUpdatedAtLabel = useMemo(() => {
    if (!shopifyAppCredentials?.updatedAt) return "";
    const parsed = new Date(shopifyAppCredentials.updatedAt);
    if (Number.isNaN(parsed.getTime())) return shopifyAppCredentials.updatedAt;
    return parsed.toLocaleString();
  }, [shopifyAppCredentials?.updatedAt]);

  const isShopifyAppCredentialsMutating = updateShopifyAppCredentials.isPending;

  const handleSaveShopifyAppCredentials = async () => {
    if (!workspaceId) {
      toast.error("Select a workspace before saving Shopify app credentials.");
      return;
    }
    const nextApiKey = shopifyAppApiKeyDraft.trim();
    const nextApiSecret = shopifyAppApiSecretDraft.trim();
    if (!nextApiKey) {
      toast.error("Shopify app API key is required.");
      return;
    }
    if (!nextApiSecret) {
      toast.error("Shopify app API secret is required.");
      return;
    }
    await updateShopifyAppCredentials.mutateAsync({
      apiKey: nextApiKey,
      apiSecret: nextApiSecret,
    });
    setShopifyAppApiSecretDraft("");
    await refetchShopifyAppCredentials();
  };

  return {
    shopifyAppApiKeyDraft,
    setShopifyAppApiKeyDraft,
    shopifyAppApiSecretDraft,
    setShopifyAppApiSecretDraft,
    hasConfiguredShopifyAppCredentials,
    isLoadingShopifyAppCredentials,
    shopifyAppCredentialsUpdatedAtLabel,
    isShopifyAppCredentialsMutating,
    handleSaveShopifyAppCredentials,
  };
}
