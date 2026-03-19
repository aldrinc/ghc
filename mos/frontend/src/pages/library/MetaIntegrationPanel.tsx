import { useEffect, useState } from "react";
import { useApiClient, type ApiError } from "@/api/client";
import { useMetaApi } from "@/api/meta";
import { useExperiments } from "@/api/experiments";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useMetaConfig } from "@/hooks/useMetaConfig";
import { useMetaInventory } from "@/hooks/useMetaInventory";
import type { Campaign } from "@/types/common";
import type { MetaPipelineAsset } from "@/types/meta";
import {
  MetaConfigSection,
  ConnectAccountForm,
  ConnectionsTable,
  CampaignPipelineSection,
  MetaInventorySection,
} from "./meta";

const defaultStatuses = ["approved"];

export function MetaIntegrationPanel() {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { listPipelineAssets } = useMetaApi();

  const meta = useMetaConfig(workspace?.id);
  const metaAdAccountId = meta.config?.connection.adAccountId ?? undefined;

  const inv = useMetaInventory({
    workspaceId: workspace?.id,
    configId: meta.config?.id,
    metaAdAccountId,
  });

  // Campaigns
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [campaignId, setCampaignId] = useState("");
  const [experimentId, setExperimentId] = useState("");
  const [statuses, setStatuses] = useState<string[]>(defaultStatuses);

  // Pipeline
  const [pipeline, setPipeline] = useState<MetaPipelineAsset[]>([]);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  const { data: experiments = [] } = useExperiments({
    clientId: workspace?.id,
    productId: product?.id,
    campaignId: campaignId || undefined,
  });

  // Load campaigns
  useEffect(() => {
    if (!workspace?.id || !product?.id) {
      setCampaigns([]);
      setCampaignError(null);
      return;
    }
    let cancelled = false;
    setCampaignError(null);
    get<Campaign[]>(`/campaigns?client_id=${workspace.id}&product_id=${product.id}`)
      .then((data) => {
        if (cancelled) return;
        setCampaigns(data);
      })
      .catch((err: ApiError) => {
        if (cancelled) return;
        setCampaignError(err?.message || "Failed to load campaigns");
      });
    return () => {
      cancelled = true;
    };
  }, [get, product?.id, workspace?.id]);

  // Load pipeline assets
  useEffect(() => {
    if (!workspace?.id || !product?.id) {
      setPipeline([]);
      setPipelineError(null);
      setPipelineLoading(false);
      return;
    }
    let cancelled = false;
    setPipelineLoading(true);
    setPipelineError(null);
    listPipelineAssets({
      clientId: workspace.id,
      productId: product.id,
      campaignId: campaignId || undefined,
      experimentId: experimentId || undefined,
      metaConfigId: meta.config?.id || undefined,
      statuses,
    })
      .then((data) => {
        if (cancelled) return;
        setPipeline(data);
      })
      .catch((err: ApiError) => {
        if (cancelled) return;
        setPipelineError(err?.message || "Failed to load pipeline assets");
        setPipeline([]);
      })
      .finally(() => {
        if (cancelled) return;
        setPipelineLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [campaignId, meta.config?.id, experimentId, listPipelineAssets, product?.id, statuses, workspace?.id]);

  const productSelected = Boolean(product?.id);

  return (
    <div className="space-y-4">
      <MetaConfigSection
        hasWorkspace={Boolean(workspace)}
        config={meta.config}
        workspaceConfigs={meta.workspaceConfigs}
        configError={meta.configError}
        configPending={meta.configPending}
        setupError={meta.setupError}
        onSelectConfig={(id) => void meta.handleSelectWorkspaceConfig(id)}
        onValidateActiveConfig={() => void meta.handleValidateActiveWorkspaceConfig()}
      />

      {workspace ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,420px),1fr]">
          <ConnectAccountForm
            formState={meta.formState}
            onFieldChange={meta.setFormField}
            onSubmit={() => void meta.handleCreateAndAttachConnection()}
            disabled={meta.setupPending}
          />
          <ConnectionsTable
            connections={meta.connections}
            workspaceConfigs={meta.workspaceConfigs}
            workspaceId={workspace.id}
            connectionAccessTokens={meta.connectionAccessTokens}
            onAccessTokenChange={meta.setConnectionAccessToken}
            onValidate={(id) => void meta.handleValidateConnection(id)}
            onAttach={(conn) => void meta.handleAttachExistingConnection(conn)}
            onUpdateCredentials={(conn) => void meta.handleUpdateConnectionCredentials(conn)}
            disabled={meta.setupPending}
          />
        </div>
      ) : null}

      <CampaignPipelineSection
        hasWorkspace={Boolean(workspace)}
        productSelected={productSelected}
        campaigns={campaigns}
        campaignId={campaignId}
        onCampaignChange={setCampaignId}
        campaignError={campaignError}
        experiments={experiments}
        experimentId={experimentId}
        onExperimentChange={setExperimentId}
        statuses={statuses}
        onStatusChange={setStatuses}
        pipeline={pipeline}
        pipelineLoading={pipelineLoading}
        pipelineError={pipelineError}
      />

      <MetaInventorySection
        inventoryTab={inv.inventoryTab}
        onTabChange={inv.setInventoryTab}
        inventory={inv.inventory}
        inventoryLoading={inv.inventoryLoading}
        inventoryError={inv.inventoryError}
        inventoryFetchedAt={inv.inventoryFetchedAt}
        onRefresh={inv.refreshInventory}
        hasConfig={Boolean(meta.config)}
        canRefresh={Boolean(metaAdAccountId && workspace?.id && meta.config?.id)}
      />
    </div>
  );
}
