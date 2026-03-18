import { useEffect, useState } from "react";
import { toast } from "@/components/ui/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ShopDomainOption } from "@/hooks/useShopifyConnection";

type ShopifyConnectionCardProps = {
  workspaceId: string;
  shopifyStatus: ReturnType<typeof import("@/hooks/useShopifyConnection").useShopifyConnection>["shopifyStatus"];
  isLoadingShopifyStatus: boolean;
  refetchShopifyStatus: () => void;
  shopifyState: string;
  installationState: string;
  shopDomainOptions: ShopDomainOption[];
  connectedShopDomains: string[];
  hasShopifyConnectionTarget: boolean;
  shopifyStatusTone: "success" | "neutral" | "danger";
  shopifyStatusLabel: string;
  shopifyStatusMessage: string;
  installationStatusLabel: string;
  isShopifyConnectionMutating: boolean;
  createShopifyInstallUrl: any;
  setDefaultShop: any;
  autoProvisionShopifyStorefrontToken: any;
  updateShopifyInstallation: any;
  disconnectShopifyInstallation: any;
};

export function ShopifyConnectionCard({
  workspaceId,
  shopifyStatus,
  isLoadingShopifyStatus,
  refetchShopifyStatus,
  shopifyState,
  installationState,
  shopDomainOptions,
  connectedShopDomains,
  hasShopifyConnectionTarget,
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
}: ShopifyConnectionCardProps) {
  const [shopifyShopDomainDraft, setShopifyShopDomainDraft] = useState("");
  const [defaultShopDomainDraft, setDefaultShopDomainDraft] = useState("");
  const [storefrontAccessTokenDraft, setStorefrontAccessTokenDraft] = useState("");
  const [showManualStorefrontTokenInput, setShowManualStorefrontTokenInput] = useState(false);

  // Seed shopifyShopDomainDraft from shopifyStatus
  useEffect(() => {
    const connectedShopDomainCandidates = [
      shopifyStatus?.selectedShopDomain,
      shopifyStatus?.shopDomain,
      ...(shopifyStatus?.shopDomains || []),
    ];
    const nextConnectedShopDomain =
      connectedShopDomainCandidates.find(
        (candidate): candidate is string => typeof candidate === "string" && Boolean(candidate.trim())
      ) || "";
    if (!nextConnectedShopDomain) return;
    setShopifyShopDomainDraft((current) => (current.trim() ? current : nextConnectedShopDomain));
  }, [shopifyStatus?.selectedShopDomain, shopifyStatus?.shopDomain, shopifyStatus?.shopDomains]);

  // Seed defaultShopDomainDraft from shopifyStatus
  useEffect(() => {
    if (!shopifyStatus?.shopDomains?.length) return;
    setDefaultShopDomainDraft((current) => {
      if (current.trim()) return current;
      if (shopifyStatus.selectedShopDomain) return shopifyStatus.selectedShopDomain;
      return shopifyStatus.shopDomains[0] || "";
    });
  }, [shopifyStatus?.selectedShopDomain, shopifyStatus?.shopDomains]);

  // Reset manual token state when shopifyState leaves installed_missing_storefront_token
  useEffect(() => {
    if (shopifyState !== "installed_missing_storefront_token") {
      setShowManualStorefrontTokenInput(false);
      setStorefrontAccessTokenDraft("");
    }
  }, [shopifyState]);

  const handleConnectShopify = async () => {
    if (!workspaceId) {
      toast.error("Select a workspace before connecting Shopify.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    const response = await createShopifyInstallUrl.mutateAsync({ shopDomain: nextDomain });
    const installUrl = response.installUrl?.trim() || "";
    if (!installUrl) {
      throw new Error("Install URL is missing from response.");
    }
    window.location.assign(installUrl);
  };

  const handleSetStorefrontToken = async () => {
    if (!workspaceId) {
      toast.error("Select a workspace before updating Shopify installation.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    const nextToken = storefrontAccessTokenDraft.trim();
    if (!nextToken) {
      toast.error("Storefront access token is required.");
      return;
    }
    await updateShopifyInstallation.mutateAsync({
      shopDomain: nextDomain,
      storefrontAccessToken: nextToken,
    });
    setStorefrontAccessTokenDraft("");
    setShowManualStorefrontTokenInput(false);
    await refetchShopifyStatus();
  };

  const handleRetryAutomaticStorefrontTokenSetup = async () => {
    if (!workspaceId) {
      toast.error("Select a workspace before updating Shopify installation.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    await autoProvisionShopifyStorefrontToken.mutateAsync({ shopDomain: nextDomain });
    setStorefrontAccessTokenDraft("");
    setShowManualStorefrontTokenInput(false);
    await refetchShopifyStatus();
  };

  const handleSetDefaultShop = async () => {
    if (!workspaceId) {
      toast.error("Select a workspace before setting default Shopify store.");
      return;
    }
    const nextDomain = defaultShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Select a Shopify shop domain.");
      return;
    }
    await setDefaultShop.mutateAsync({ shopDomain: nextDomain });
    await refetchShopifyStatus();
  };

  const handleDisconnectShopify = async () => {
    if (!workspaceId) {
      toast.error("Select a workspace before disconnecting Shopify.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    await disconnectShopifyInstallation.mutateAsync({ shopDomain: nextDomain });
    setStorefrontAccessTokenDraft("");
    await refetchShopifyStatus();
  };

  return (
    <div className="ds-card ds-card--md space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-content">Store connection</div>
        <Badge tone={shopifyStatusTone}>{isLoadingShopifyStatus ? "Checking\u2026" : shopifyStatusLabel}</Badge>
      </div>

      {/* Connected state */}
      {hasShopifyConnectionTarget ? (
        <div className="space-y-3">
          <div className="flex items-center gap-3 rounded-md border border-divider bg-surface-2 px-3 py-2">
            <div className="min-w-0 flex-1">
              <div className="text-sm text-content truncate">
                {connectedShopDomains.length ? connectedShopDomains.join(", ") : shopifyShopDomainDraft}
              </div>
              <div className="text-xs text-content-muted">{shopifyStatusMessage}</div>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void refetchShopifyStatus()}
                disabled={isLoadingShopifyStatus || isShopifyConnectionMutating}
              >
                Refresh
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => void handleDisconnectShopify()}
                disabled={!workspaceId || !shopifyShopDomainDraft.trim() || isShopifyConnectionMutating}
              >
                {disconnectShopifyInstallation.isPending ? "Disconnecting\u2026" : "Disconnect"}
              </Button>
            </div>
          </div>

          {shopifyStatus?.missingScopes?.length ? (
            <div className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
              Missing scopes: {shopifyStatus.missingScopes.join(", ")}
            </div>
          ) : null}

          {shopifyState === "multiple_installations_conflict" && shopifyStatus?.shopDomains?.length ? (
            <div className="space-y-1">
              <div className="text-xs text-content-muted">Multiple installations detected. Choose a default store:</div>
              <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                <select
                  className="w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content shadow-sm"
                  value={defaultShopDomainDraft}
                  onChange={(e) => setDefaultShopDomainDraft(e.target.value)}
                  disabled={setDefaultShop.isPending || disconnectShopifyInstallation.isPending}
                >
                  {shopDomainOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void handleSetDefaultShop()}
                  disabled={!defaultShopDomainDraft.trim() || setDefaultShop.isPending || disconnectShopifyInstallation.isPending}
                >
                  {setDefaultShop.isPending ? "Saving\u2026" : "Set default"}
                </Button>
              </div>
            </div>
          ) : null}

          {shopifyState === "installed_missing_storefront_token" ? (
            <div className="space-y-2 rounded-md border border-divider bg-surface-2 px-3 py-2">
              <div className="text-xs text-content-muted">Storefront access token is missing.</div>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void handleRetryAutomaticStorefrontTokenSetup()}
                  disabled={!workspaceId || !shopifyShopDomainDraft.trim() || isShopifyConnectionMutating}
                >
                  {autoProvisionShopifyStorefrontToken.isPending ? "Retrying\u2026" : "Retry automatic setup"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowManualStorefrontTokenInput((current) => !current)}
                  disabled={isShopifyConnectionMutating}
                >
                  {showManualStorefrontTokenInput ? "Cancel" : "Enter manually"}
                </Button>
              </div>
              {showManualStorefrontTokenInput ? (
                <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                  <Input
                    type="password"
                    placeholder="Storefront access token"
                    value={storefrontAccessTokenDraft}
                    onChange={(e) => setStorefrontAccessTokenDraft(e.target.value)}
                    disabled={isShopifyConnectionMutating}
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void handleSetStorefrontToken()}
                    disabled={
                      !workspaceId ||
                      !shopifyShopDomainDraft.trim() ||
                      !storefrontAccessTokenDraft.trim() ||
                      isShopifyConnectionMutating
                    }
                  >
                    {updateShopifyInstallation.isPending ? "Saving\u2026" : "Save token"}
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : (
        /* Not connected state */
        <div className="space-y-2">
          <div className="text-xs text-content-muted">
            Enter your Shopify store domain to connect.
          </div>
          <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
            <Input
              placeholder="example-shop.myshopify.com"
              value={shopifyShopDomainDraft}
              onChange={(e) => setShopifyShopDomainDraft(e.target.value)}
              disabled={isShopifyConnectionMutating}
            />
            <Button
              size="sm"
              onClick={() => void handleConnectShopify()}
              disabled={!workspaceId || !shopifyShopDomainDraft.trim() || isShopifyConnectionMutating}
            >
              {createShopifyInstallUrl.isPending ? "Redirecting\u2026" : "Connect"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
