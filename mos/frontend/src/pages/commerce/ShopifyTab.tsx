import { useMemo } from "react";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { useDesignSystems } from "@/api/designSystems";
import { useShopifyAppCredentials } from "@/hooks/useShopifyAppCredentials";
import { useShopifyConnection } from "@/hooks/useShopifyConnection";
import { ShopifyAppCredentialsCard } from "@/components/commerce/ShopifyAppCredentialsCard";
import { ShopifyConnectionCard } from "@/components/commerce/ShopifyConnectionCard";
import { SiteImportsCard } from "@/components/commerce/SiteImportsCard";
import { ThemeTemplateWorkflowCard } from "@/components/commerce/ThemeTemplateWorkflowCard";
import { CompliancePolicyCard } from "@/components/commerce/CompliancePolicyCard";

export function ShopifyTab() {
  const { workspace } = useWorkspace();
  const { product: activeWorkspaceProduct, products: workspaceProducts } = useProductContext();
  const { data: designSystems = [], isLoading: isLoadingDesignSystems } = useDesignSystems(workspace?.id);
  const appCredentials = useShopifyAppCredentials(workspace?.id);
  const connection = useShopifyConnection(workspace?.id);

  const designSystemOptions = useMemo(
    () => [
      { label: "Workspace default", value: "" },
      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
    ],
    [designSystems],
  );

  if (!workspace) return null;

  const isConnected = connection.hasShopifyConnectionTarget;

  return (
    <div className="space-y-4">
      <ShopifyAppCredentialsCard
        workspaceId={workspace.id}
        shopifyAppApiKeyDraft={appCredentials.shopifyAppApiKeyDraft}
        setShopifyAppApiKeyDraft={appCredentials.setShopifyAppApiKeyDraft}
        shopifyAppApiSecretDraft={appCredentials.shopifyAppApiSecretDraft}
        setShopifyAppApiSecretDraft={appCredentials.setShopifyAppApiSecretDraft}
        hasConfiguredShopifyAppCredentials={appCredentials.hasConfiguredShopifyAppCredentials}
        isLoadingShopifyAppCredentials={appCredentials.isLoadingShopifyAppCredentials}
        shopifyAppCredentialsUpdatedAtLabel={appCredentials.shopifyAppCredentialsUpdatedAtLabel}
        isShopifyAppCredentialsMutating={appCredentials.isShopifyAppCredentialsMutating}
        hasShopifyConnectionTarget={connection.hasShopifyConnectionTarget}
        onSave={appCredentials.handleSaveShopifyAppCredentials}
      />

      <ShopifyConnectionCard
        workspaceId={workspace.id}
        hasConfiguredShopifyAppCredentials={appCredentials.hasConfiguredShopifyAppCredentials}
        shopifyStatus={connection.shopifyStatus}
        isLoadingShopifyStatus={connection.isLoadingShopifyStatus}
        refetchShopifyStatus={connection.refetchShopifyStatus}
        shopifyState={connection.shopifyState}
        installationState={connection.installationState}
        shopDomainOptions={connection.shopDomainOptions}
        connectedShopDomains={connection.connectedShopDomains}
        hasShopifyConnectionTarget={connection.hasShopifyConnectionTarget}
        shopifyStatusTone={connection.shopifyStatusTone}
        shopifyStatusLabel={connection.shopifyStatusLabel}
        shopifyStatusMessage={connection.shopifyStatusMessage}
        installationStatusLabel={connection.installationStatusLabel}
        isShopifyConnectionMutating={connection.isShopifyConnectionMutating}
        createShopifyInstallUrl={connection.createShopifyInstallUrl}
        setDefaultShop={connection.setDefaultShop}
        autoProvisionShopifyStorefrontToken={connection.autoProvisionShopifyStorefrontToken}
        updateShopifyInstallation={connection.updateShopifyInstallation}
        disconnectShopifyInstallation={connection.disconnectShopifyInstallation}
      />

      <SiteImportsCard workspaceId={workspace.id} activeWorkspaceProduct={activeWorkspaceProduct} />

      {isConnected ? (
        <>
          <ThemeTemplateWorkflowCard
            workspaceId={workspace.id}
            shopifySyncShopDomain={connection.shopifySyncShopDomain}
            designSystemOptions={designSystemOptions}
            isLoadingDesignSystems={isLoadingDesignSystems}
            workspaceProducts={workspaceProducts}
            activeWorkspaceProduct={activeWorkspaceProduct}
          />

          <CompliancePolicyCard
            workspaceId={workspace.id}
            workspaceName={workspace.name || ""}
            shopifySyncShopDomain={connection.shopifySyncShopDomain}
            selectedShopDomainOption={connection.selectedShopDomainOption}
            hasShopifyConnectionTarget={connection.hasShopifyConnectionTarget}
          />
        </>
      ) : (
        <div className="ds-card ds-card--md">
          <div className="text-xs text-content-muted">
            Connect your Shopify store above to access theme templates and compliance tools.
          </div>
        </div>
      )}
    </div>
  );
}
