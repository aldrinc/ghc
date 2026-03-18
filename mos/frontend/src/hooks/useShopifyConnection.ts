import { useEffect, useMemo, useState } from "react";
import {
  useClientShopifyStatus,
  useCreateClientShopifyInstallUrl,
  useSetClientShopifyDefaultShop,
  useAutoProvisionClientShopifyStorefrontToken,
  useUpdateClientShopifyInstallation,
  useDisconnectClientShopifyInstallation,
} from "@/api/clients";

export type ShopDomainOption = {
  label: string;
  storefrontDomain: string;
  value: string;
};

export function useShopifyConnection(workspaceId: string | undefined) {
  const {
    data: shopifyStatus,
    isLoading: isLoadingShopifyStatus,
    refetch: refetchShopifyStatus,
    error: shopifyStatusError,
  } = useClientShopifyStatus(workspaceId);

  const createShopifyInstallUrl = useCreateClientShopifyInstallUrl(workspaceId || "");
  const setDefaultShop = useSetClientShopifyDefaultShop(workspaceId || "");
  const autoProvisionShopifyStorefrontToken = useAutoProvisionClientShopifyStorefrontToken(
    workspaceId || "",
  );
  const updateShopifyInstallation = useUpdateClientShopifyInstallation(workspaceId || "");
  const disconnectShopifyInstallation = useDisconnectClientShopifyInstallation(workspaceId || "");

  const [shopifySyncShopDomain, setShopifySyncShopDomain] = useState("");

  const shopifyState = shopifyStatus?.state || "error";
  const installationState = shopifyStatus?.installationState || "not_installed";

  const shopDomainOptions = useMemo((): ShopDomainOption[] => {
    const displayByShopDomain = new Map<string, string>();
    const addCandidate = (
      shopDomain: string | null | undefined,
      displayShopDomain?: string | null | undefined,
    ) => {
      if (typeof shopDomain !== "string") return;
      const normalized = shopDomain.trim().toLowerCase();
      if (!normalized) return;
      const normalizedDisplay =
        typeof displayShopDomain === "string" && displayShopDomain.trim()
          ? displayShopDomain.trim().toLowerCase()
          : normalized;
      displayByShopDomain.set(normalized, normalizedDisplay);
    };

    (shopifyStatus?.shopDomains || []).forEach((shopDomain, index) =>
      addCandidate(shopDomain, shopifyStatus?.displayShopDomains?.[index]),
    );
    addCandidate(shopifyStatus?.selectedShopDomain, shopifyStatus?.selectedShopDomain);
    addCandidate(shopifyStatus?.shopDomain, shopifyStatus?.displayShopDomain || shopifyStatus?.shopDomain);

    return Array.from(displayByShopDomain.entries())
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([shopDomain, storefrontDomain]) => ({
        label: storefrontDomain,
        storefrontDomain,
        value: shopDomain,
      }));
  }, [
    shopifyStatus?.displayShopDomain,
    shopifyStatus?.displayShopDomains,
    shopifyStatus?.selectedShopDomain,
    shopifyStatus?.shopDomain,
    shopifyStatus?.shopDomains,
  ]);

  const connectedShopDomains = useMemo(() => {
    const displayShopDomains = (shopifyStatus?.displayShopDomains || [])
      .map((shopDomain) => shopDomain.trim().toLowerCase())
      .filter(Boolean);
    if (displayShopDomains.length) return displayShopDomains;
    return (shopifyStatus?.shopDomains || []).map((shopDomain) => shopDomain.trim().toLowerCase()).filter(Boolean);
  }, [shopifyStatus?.displayShopDomains, shopifyStatus?.shopDomains]);

  const selectedShopDomainOption = useMemo(
    () => shopDomainOptions.find((option) => option.value === shopifySyncShopDomain) || null,
    [shopDomainOptions, shopifySyncShopDomain],
  );

  const hasShopifyConnectionTarget = shopDomainOptions.length > 0;

  const shopifyStatusTone = useMemo(() => {
    if (shopifyState === "ready") return "success" as const;
    if (shopifyState === "not_connected" || shopifyState === "installed_missing_storefront_token")
      return "neutral" as const;
    return "danger" as const;
  }, [shopifyState]);

  const shopifyStatusLabel = useMemo(() => {
    if (shopifyState === "ready") return "Ready";
    if (shopifyState === "not_connected") return "Not connected";
    if (shopifyState === "installed_missing_storefront_token") return "Missing token";
    if (shopifyState === "multiple_installations_conflict") return "Store conflict";
    return "Error";
  }, [shopifyState]);

  const shopifyStatusMessage = useMemo(() => {
    if (shopifyStatus?.message) return shopifyStatus.message;
    if (shopifyStatusError && typeof shopifyStatusError === "object" && "message" in shopifyStatusError) {
      const message = (shopifyStatusError as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return message;
    }
    const fallbackErrorMessage = String(shopifyStatusError ?? "").trim();
    if (fallbackErrorMessage) return fallbackErrorMessage;
    return "Checking Shopify connection status.";
  }, [shopifyStatus?.message, shopifyStatusError]);

  const installationStatusLabel = useMemo(() => {
    if (installationState === "installed") return "Installed";
    if (installationState === "installed_missing_storefront_token") return "Installed (missing token)";
    if (installationState === "conflict") return "Conflict";
    if (installationState === "error") return "Error";
    return "Not installed";
  }, [installationState]);

  const isShopifyConnectionMutating =
    createShopifyInstallUrl.isPending ||
    autoProvisionShopifyStorefrontToken.isPending ||
    updateShopifyInstallation.isPending ||
    disconnectShopifyInstallation.isPending ||
    setDefaultShop.isPending;

  // Resolve the default shopifySyncShopDomain when options change
  useEffect(() => {
    if (!shopDomainOptions.length) {
      setShopifySyncShopDomain("");
      return;
    }
    const resolveNextShopDomain = (current: string) => {
      if (current && shopDomainOptions.some((option) => option.value === current)) return current;
      const selectedShopDomain = shopifyStatus?.selectedShopDomain?.trim().toLowerCase();
      if (selectedShopDomain && shopDomainOptions.some((option) => option.value === selectedShopDomain)) {
        return selectedShopDomain;
      }
      const readyShopDomain = shopifyStatus?.shopDomain?.trim().toLowerCase();
      if (readyShopDomain && shopDomainOptions.some((option) => option.value === readyShopDomain)) {
        return readyShopDomain;
      }
      return shopDomainOptions[0]?.value || "";
    };
    setShopifySyncShopDomain(resolveNextShopDomain);
  }, [shopDomainOptions, shopifyStatus?.selectedShopDomain, shopifyStatus?.shopDomain]);

  // Reset on workspace change
  useEffect(() => {
    setShopifySyncShopDomain("");
  }, [workspaceId]);

  return {
    shopifyStatus,
    isLoadingShopifyStatus,
    refetchShopifyStatus,
    shopifyStatusError,
    shopifyState,
    installationState,
    shopDomainOptions,
    connectedShopDomains,
    selectedShopDomainOption,
    hasShopifyConnectionTarget,
    shopifySyncShopDomain,
    setShopifySyncShopDomain,
    shopifyStatusTone,
    shopifyStatusLabel,
    shopifyStatusMessage,
    installationStatusLabel,
    isShopifyConnectionMutating,
    createShopifyInstallUrl,
    setDefaultShop,
    autoProvisionShopifyStorefrontToken,
    updateShopifyInstallation,
    disconnectShopifyInstallation,
  };
}
