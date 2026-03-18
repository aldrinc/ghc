import { useEffect, useMemo, useState } from "react";
import { useApiClient, type ApiError } from "@/api/client";
import { useMetaApi } from "@/api/meta";
import { useExperiments } from "@/api/experiments";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { MediaTile } from "@/components/library/MediaViewer";
import { StatusBadge } from "@/components/StatusBadge";
import type { Campaign } from "@/types/common";
import type {
  MetaAdAccountConnection,
  MetaPipelineAsset,
  MetaRemoteAd,
  MetaRemoteAdSet,
  MetaRemoteCampaign,
  MetaRemoteCreative,
  MetaRemoteImage,
  MetaRemoteVideo,
  MetaWorkspaceAdConfig,
} from "@/types/meta";
import type { MediaAsset } from "@/types/library";

type InventoryTab = "images" | "videos" | "creatives" | "campaigns" | "adsets" | "ads";

type RemotePayload =
  | { data: MetaRemoteImage[] }
  | { data: MetaRemoteVideo[] }
  | { data: MetaRemoteCreative[] }
  | { data: MetaRemoteCampaign[] }
  | { data: MetaRemoteAdSet[] }
  | { data: MetaRemoteAd[] };

const inventoryTabs: { key: InventoryTab; label: string }[] = [
  { key: "images", label: "Images" },
  { key: "videos", label: "Videos" },
  { key: "creatives", label: "Creatives" },
  { key: "campaigns", label: "Campaigns" },
  { key: "adsets", label: "Ad Sets" },
  { key: "ads", label: "Ads" },
];

const defaultStatuses = ["approved"];

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function shortId(value?: string | null, size = 6) {
  if (!value) return "—";
  return value.length > size * 2 ? `${value.slice(0, size)}…${value.slice(-size)}` : value;
}

function stepClass(status?: string | null) {
  if (!status || status === "missing") return "border-border bg-muted text-content-muted";
  if (["draft", "pending"].includes(status)) return "border-warning/30 bg-warning/10 text-warning";
  if (["ready", "uploaded", "approved", "active"].includes(status)) return "border-success/30 bg-success/10 text-success";
  return "border-border bg-surface-2 text-content";
}

function PipelineStep({ label, status, count }: { label: string; status?: string | null; count?: number }) {
  const resolved = status || "missing";
  return (
    <div className={`rounded-md border px-2 py-1 text-xs font-semibold ${stepClass(resolved)}`}>
      {label}: {resolved}
      {typeof count === "number" ? ` · ${count}` : ""}
    </div>
  );
}

function buildMediaAsset(item: MetaPipelineAsset): MediaAsset | undefined {
  const url = item.asset.public_url;
  if (!url) return undefined;
  const isVideo = item.asset.content_type?.startsWith("video/");
  if (isVideo) {
    return { type: "video", url, posterUrl: url };
  }
  return { type: "image", url, thumbUrl: url, alt: item.asset.asset_kind || "Creative asset" };
}

export function MetaIntegrationPanel() {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const {
    createConnection,
    createWorkspaceConfig,
    getActiveConfig,
    listPipelineAssets,
    listConnections,
    listWorkspaceConfigs,
    listRemoteImages,
    listRemoteVideos,
    listRemoteCreatives,
    listRemoteCampaigns,
    listRemoteAdSets,
    listRemoteAds,
    selectWorkspaceConfig,
    updateConnection,
    validateConnection,
  } = useMetaApi();
  const [config, setConfig] = useState<MetaWorkspaceAdConfig | null>(null);
  const [workspaceConfigs, setWorkspaceConfigs] = useState<MetaWorkspaceAdConfig[]>([]);
  const [connections, setConnections] = useState<MetaAdAccountConnection[]>([]);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configPending, setConfigPending] = useState(false);
  const [setupPending, setSetupPending] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [newConnectionName, setNewConnectionName] = useState("");
  const [newConnectionAdAccountId, setNewConnectionAdAccountId] = useState("");
  const [newConnectionAdAccountName, setNewConnectionAdAccountName] = useState("");
  const [newConnectionAccessToken, setNewConnectionAccessToken] = useState("");
  const [newConnectionGraphApiVersion, setNewConnectionGraphApiVersion] = useState("v24.0");
  const [connectionAccessTokens, setConnectionAccessTokens] = useState<Record<string, string>>({});
  const [newWorkspaceConfigName, setNewWorkspaceConfigName] = useState("");
  const [newWorkspacePageId, setNewWorkspacePageId] = useState("");
  const [newWorkspacePixelId, setNewWorkspacePixelId] = useState("");
  const [newWorkspaceVerifiedDomain, setNewWorkspaceVerifiedDomain] = useState("");
  const [newWorkspaceTrackingParams, setNewWorkspaceTrackingParams] = useState("utm_source=meta&utm_medium=paid");
  const metaAdAccountId = config?.connection.adAccountId;
  const metaConfigLoading = !config && !configError;

  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [campaignId, setCampaignId] = useState("");
  const [experimentId, setExperimentId] = useState("");
  const [statuses, setStatuses] = useState<string[]>(defaultStatuses);
  const [pipeline, setPipeline] = useState<MetaPipelineAsset[]>([]);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  const [inventoryTab, setInventoryTab] = useState<InventoryTab>("images");
  const [inventory, setInventory] = useState<RemotePayload | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [inventoryFetchedAt, setInventoryFetchedAt] = useState<string | null>(null);

  const { data: experiments = [] } = useExperiments({
    clientId: workspace?.id,
    productId: product?.id,
    campaignId: campaignId || undefined,
  });

  useEffect(() => {
    if (!workspace?.id) {
      setConfig(null);
      setWorkspaceConfigs([]);
      setConnections([]);
      setConfigError(null);
      return;
    }
    let cancelled = false;

    const loadMetaState = async () => {
      try {
        const [connectionRows, workspaceConfigRows] = await Promise.all([
          listConnections(),
          listWorkspaceConfigs(workspace.id),
        ]);
        if (cancelled) return;
        setConnections(connectionRows);
        setWorkspaceConfigs(workspaceConfigRows);
        try {
          const active = await getActiveConfig(workspace.id);
          if (cancelled) return;
          setConfig(active);
          setConfigError(null);
        } catch (err) {
          if (cancelled) return;
          setConfig(null);
          setConfigError((err as ApiError)?.message || "No active Meta config selected for this workspace");
        }
      } catch (err) {
        if (cancelled) return;
        setConnections([]);
        setWorkspaceConfigs([]);
        setConfig(null);
        setConfigError((err as ApiError)?.message || "Failed to load Meta setup");
      }
    };

    void loadMetaState();
    return () => {
      cancelled = true;
    };
  }, [getActiveConfig, listConnections, listWorkspaceConfigs, workspace?.id]);

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
      metaConfigId: config?.id || undefined,
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
  }, [campaignId, config?.id, experimentId, listPipelineAssets, product?.id, statuses, workspace?.id]);

  const refreshMetaState = async () => {
    if (!workspace?.id) return;
    const [connectionRows, workspaceConfigRows] = await Promise.all([
      listConnections(),
      listWorkspaceConfigs(workspace.id),
    ]);
    setConnections(connectionRows);
    setWorkspaceConfigs(workspaceConfigRows);
    try {
      const active = await getActiveConfig(workspace.id);
      setConfig(active);
      setConfigError(null);
    } catch (err) {
      setConfig(null);
      setConfigError((err as ApiError)?.message || "No active Meta config selected for this workspace");
    }
  };

  const handleSelectWorkspaceConfig = async (configId: string) => {
    if (!workspace?.id || !configId) return;
    setConfigPending(true);
    setConfigError(null);
    try {
      const active = await selectWorkspaceConfig(workspace.id, configId);
      setConfig(active);
      setWorkspaceConfigs((current) =>
        current.map((entry) => ({
          ...entry,
          isDefault: entry.id === active.id,
        })),
      );
    } catch (err) {
      setConfigError((err as ApiError)?.message || "Failed to activate workspace Meta config");
    } finally {
      setConfigPending(false);
    }
  };

  const handleCreateAndAttachConnection = async () => {
    if (!workspace?.id) return;
    setSetupPending(true);
    setSetupError(null);
    try {
      const connection = await createConnection({
        name: newConnectionName.trim() || newConnectionAdAccountName.trim() || "Meta connection",
        adAccountId: newConnectionAdAccountId.trim() || undefined,
        adAccountName: newConnectionAdAccountName.trim() || undefined,
        accessToken: newConnectionAccessToken.trim(),
        graphApiVersion: newConnectionGraphApiVersion.trim() || "v24.0",
        graphApiBaseUrl: "https://graph.facebook.com",
        status: "active",
        metadata: {},
      });
      await createWorkspaceConfig(workspace.id, {
        connectionId: connection.id,
        name: newWorkspaceConfigName.trim() || newConnectionName.trim() || "Meta workspace config",
        isDefault: workspaceConfigs.length === 0,
        pageId: newWorkspacePageId.trim() || undefined,
        pixelId: newWorkspacePixelId.trim() || undefined,
        verifiedDomain: newWorkspaceVerifiedDomain.trim() || undefined,
        trackingUrlParameters: newWorkspaceTrackingParams.trim() || undefined,
        status: "active",
        metadata: {},
      });
      setNewConnectionName("");
      setNewConnectionAdAccountId("");
      setNewConnectionAdAccountName("");
      setNewConnectionAccessToken("");
      setNewWorkspaceConfigName("");
      setNewWorkspacePageId("");
      setNewWorkspacePixelId("");
      setNewWorkspaceVerifiedDomain("");
      await refreshMetaState();
    } catch (err) {
      setSetupError((err as ApiError)?.message || "Failed to create Meta connection");
    } finally {
      setSetupPending(false);
    }
  };

  const handleAttachExistingConnection = async (connection: MetaAdAccountConnection) => {
    if (!workspace?.id) return;
    setSetupPending(true);
    setSetupError(null);
    try {
      await createWorkspaceConfig(workspace.id, {
        connectionId: connection.id,
        name: connection.name,
        isDefault: workspaceConfigs.length === 0,
        status: "active",
        metadata: {},
      });
      await refreshMetaState();
    } catch (err) {
      setSetupError((err as ApiError)?.message || "Failed to attach Meta connection to workspace");
    } finally {
      setSetupPending(false);
    }
  };

  const handleValidateConnection = async (connectionId: string) => {
    setSetupPending(true);
    setSetupError(null);
    try {
      await validateConnection(connectionId);
      await refreshMetaState();
    } catch (err) {
      setSetupError((err as ApiError)?.message || "Failed to validate Meta connection");
    } finally {
      setSetupPending(false);
    }
  };

  const handleUpdateConnectionCredentials = async (connection: MetaAdAccountConnection) => {
    const accessToken = (connectionAccessTokens[connection.id] || "").trim();
    if (!accessToken) {
      setSetupError(`Access token is required to update '${connection.name}'.`);
      return;
    }
    setSetupPending(true);
    setSetupError(null);
    try {
      await updateConnection(connection.id, {
        name: connection.name,
        adAccountId: connection.adAccountId || undefined,
        adAccountName: connection.adAccountName || undefined,
        businessManagerId: connection.businessManagerId || undefined,
        businessManagerName: connection.businessManagerName || undefined,
        graphApiVersion: connection.graphApiVersion,
        graphApiBaseUrl: connection.graphApiBaseUrl,
        accessToken,
        tokenExpiresAt: connection.tokenExpiresAt || undefined,
        status: connection.status,
        metadata: connection.metadata || {},
      });
      setConnectionAccessTokens((current) => ({
        ...current,
        [connection.id]: "",
      }));
      await refreshMetaState();
    } catch (err) {
      setSetupError((err as ApiError)?.message || "Failed to update Meta connection credentials");
    } finally {
      setSetupPending(false);
    }
  };

  const inventoryFetcher = useMemo(() => {
    switch (inventoryTab) {
      case "videos":
        return listRemoteVideos;
      case "creatives":
        return listRemoteCreatives;
      case "campaigns":
        return listRemoteCampaigns;
      case "adsets":
        return listRemoteAdSets;
      case "ads":
        return listRemoteAds;
      case "images":
      default:
        return listRemoteImages;
    }
  }, [inventoryTab, listRemoteAds, listRemoteAdSets, listRemoteCampaigns, listRemoteCreatives, listRemoteImages, listRemoteVideos]);

  useEffect(() => {
    let cancelled = false;
    if (!metaAdAccountId || !workspace?.id || !config?.id) {
      setInventory(null);
      setInventoryError(null);
      setInventoryFetchedAt(null);
      setInventoryLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setInventoryLoading(true);
    setInventoryError(null);
    inventoryFetcher({ fetchAll: true, clientId: workspace.id, metaConfigId: config.id, adAccountId: metaAdAccountId })
      .then((data) => {
        if (cancelled) return;
        setInventory(data);
        setInventoryFetchedAt(new Date().toISOString());
      })
      .catch((err: ApiError) => {
        if (cancelled) return;
        setInventoryError(err?.message || "Failed to load Meta inventory");
        setInventory(null);
      })
      .finally(() => {
        if (cancelled) return;
        setInventoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config?.id, inventoryFetcher, metaAdAccountId, workspace?.id]);

  const statusOptions = useMemo(
    () => [
      { label: "Approved", value: "approved" },
      { label: "Draft", value: "draft" },
      { label: "Rejected", value: "rejected" },
      { label: "Pending", value: "pending" },
    ],
    []
  );

  const campaignOptions = useMemo(() => {
    const options = [{ label: "All campaigns", value: "" }];
    return options.concat(campaigns.map((c) => ({ label: c.name, value: c.id })));
  }, [campaigns]);

  const experimentOptions = useMemo(() => {
    const options = [{ label: "All angles", value: "" }];
    return options.concat(experiments.map((e) => ({ label: e.name, value: e.id })));
  }, [experiments]);

  const selectedStatus = statuses[0] || "";
  const productSelected = Boolean(product?.id);

  return (
    <div className="space-y-4">
      <div className="ds-card ds-card--md shadow-none space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-content">Meta integration</div>
            <div className="text-xs text-content-muted">
              Connect org-wide Meta ad accounts once, then attach and select them per workspace.
            </div>
          </div>
          {workspace ? (
            <div className="text-xs text-content-muted">Workspace: {workspace.name}</div>
          ) : (
            <div className="text-xs text-content-muted">Select a workspace to manage Meta setup.</div>
          )}
        </div>

        {workspace && workspaceConfigs.length ? (
          <div className="grid gap-3 md:grid-cols-[minmax(0,320px),1fr]">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Active workspace Meta config</label>
              <Select
                value={config?.id || ""}
                onValueChange={(value) => {
                  void handleSelectWorkspaceConfig(value);
                }}
                options={workspaceConfigs.map((entry) => ({
                  label: entry.isDefault ? `${entry.name} (Active)` : entry.name,
                  value: entry.id,
                }))}
                disabled={configPending}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-content-muted">
              {config ? (
                <>
                  <Badge tone="neutral">{config.name}</Badge>
                  <Badge tone="neutral">Ad Account {shortId(config.connection.adAccountId, 4)}</Badge>
                  {config.pageId ? <Badge tone="neutral">Page {shortId(config.pageId, 4)}</Badge> : null}
                  <Badge tone="neutral">{config.connection.graphApiVersion}</Badge>
                </>
              ) : configError ? (
                <span className="text-danger">{configError}</span>
              ) : (
                <span>Loading Meta config…</span>
              )}
            </div>
          </div>
        ) : workspace ? (
          <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
            {configError || "No Meta configs are attached to this workspace yet."}
          </div>
        ) : null}

        {setupError ? (
          <div className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">{setupError}</div>
        ) : null}

        {workspace ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,420px),1fr]">
            <div className="space-y-3 rounded-lg border border-border bg-surface p-4">
              <div>
                <div className="text-sm font-semibold text-content">Connect new ad account</div>
                <div className="text-xs text-content-muted">Credentials live on the reusable connection. Page and pixel stay on the workspace config.</div>
              </div>
              <Input value={newConnectionName} onChange={(event) => setNewConnectionName(event.target.value)} placeholder="Connection name" />
              <Input value={newConnectionAdAccountId} onChange={(event) => setNewConnectionAdAccountId(event.target.value)} placeholder="Ad account ID" />
              <Input value={newConnectionAdAccountName} onChange={(event) => setNewConnectionAdAccountName(event.target.value)} placeholder="Ad account name" />
              <Input value={newConnectionAccessToken} onChange={(event) => setNewConnectionAccessToken(event.target.value)} placeholder="Access token" />
              <Input
                value={newConnectionGraphApiVersion}
                onChange={(event) => setNewConnectionGraphApiVersion(event.target.value)}
                placeholder="Graph API version"
              />
              <Input value={newWorkspaceConfigName} onChange={(event) => setNewWorkspaceConfigName(event.target.value)} placeholder="Workspace config name" />
              <Input value={newWorkspacePageId} onChange={(event) => setNewWorkspacePageId(event.target.value)} placeholder="Page ID" />
              <Input value={newWorkspacePixelId} onChange={(event) => setNewWorkspacePixelId(event.target.value)} placeholder="Pixel ID" />
              <Input
                value={newWorkspaceVerifiedDomain}
                onChange={(event) => setNewWorkspaceVerifiedDomain(event.target.value)}
                placeholder="Verified domain"
              />
              <Input
                value={newWorkspaceTrackingParams}
                onChange={(event) => setNewWorkspaceTrackingParams(event.target.value)}
                placeholder="Tracking params"
              />
              <Button variant="primary" size="sm" onClick={() => void handleCreateAndAttachConnection()} disabled={setupPending}>
                {setupPending ? "Saving…" : "Connect and attach"}
              </Button>
            </div>

            <div className="space-y-3 rounded-lg border border-border bg-surface p-4">
              <div>
                <div className="text-sm font-semibold text-content">Org-connected ad accounts</div>
                <div className="text-xs text-content-muted">Reuse an existing Meta ad account across workspaces without re-entering credentials.</div>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeadCell>Connection</TableHeadCell>
                    <TableHeadCell>Usage</TableHeadCell>
                    <TableHeadCell>Actions</TableHeadCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {connections.map((connection) => {
                    const attachedToWorkspace = workspaceConfigs.some((entry) => entry.connectionId === connection.id);
                    return (
                      <TableRow key={connection.id}>
                        <TableCell>
                          <div className="space-y-1">
                            <div className="text-sm font-semibold text-content">{connection.name}</div>
                            <div className="text-xs text-content-muted">
                              {connection.adAccountName || shortId(connection.adAccountId, 4)} · {connection.graphApiVersion}
                            </div>
                            <div className="flex flex-wrap gap-1">
                              <Badge tone={connection.hasCredentials ? "success" : "danger"}>
                                {connection.hasCredentials ? "Credentials stored" : "Missing credentials"}
                              </Badge>
                              <Badge tone={connection.validationStatus === "valid" ? "success" : "neutral"}>
                                {connection.validationStatus}
                              </Badge>
                            </div>
                            {!connection.hasCredentials ? (
                              <div className="flex flex-wrap items-center gap-2 pt-2">
                                <Input
                                  value={connectionAccessTokens[connection.id] || ""}
                                  onChange={(event) =>
                                    setConnectionAccessTokens((current) => ({
                                      ...current,
                                      [connection.id]: event.target.value,
                                    }))
                                  }
                                  placeholder="Paste access token to reconnect"
                                  className="h-8 min-w-[220px] max-w-[360px]"
                                />
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={() => void handleUpdateConnectionCredentials(connection)}
                                  disabled={setupPending || !(connectionAccessTokens[connection.id] || "").trim()}
                                >
                                  Save token
                                </Button>
                              </div>
                            ) : null}
                            {connection.lastValidationError ? (
                              <div className="text-xs text-danger">{connection.lastValidationError}</div>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {connection.usedByWorkspaces.length ? (
                              connection.usedByWorkspaces.map((usage) => (
                                <Badge key={usage.configId} tone={usage.clientId === workspace.id ? "accent" : "neutral"}>
                                  {usage.clientName}
                                </Badge>
                              ))
                            ) : (
                              <span className="text-xs text-content-muted">Unused</span>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => void handleValidateConnection(connection.id)}
                              disabled={setupPending}
                            >
                              Validate
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => void handleAttachExistingConnection(connection)}
                              disabled={setupPending || attachedToWorkspace}
                            >
                              {attachedToWorkspace ? "Attached" : "Attach to workspace"}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
        ) : null}
      </div>

      <div className="ds-card ds-card--md shadow-none space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-content">Campaign pipeline</div>
            <div className="text-xs text-content-muted">
              Track how angles and assets become Meta creatives and ads.
            </div>
          </div>
          <div className="text-xs text-content-muted">
            {workspace ? `Workspace: ${workspace.name}` : "No workspace selected"}
          </div>
        </div>

        {!workspace && (
          <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
            Select a workspace to view pipeline assets.
          </div>
        )}

        {workspace && !productSelected && (
          <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
            Select a product to view campaigns and pipeline assets for this workspace.
          </div>
        )}

        {workspace && (
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Campaign</label>
              <Select
                value={campaignId}
                onValueChange={setCampaignId}
                options={campaignOptions}
                disabled={!productSelected}
              />
              {campaignError && <div className="text-xs text-danger">{campaignError}</div>}
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Angle</label>
              <Select
                value={experimentId}
                onValueChange={setExperimentId}
                options={experimentOptions}
                disabled={!productSelected}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Asset status</label>
              <Select
                value={selectedStatus}
                onValueChange={(value) => setStatuses(value ? [value] : [])}
                options={[{ label: "All statuses", value: "" }, ...statusOptions]}
              />
            </div>
          </div>
        )}

        {workspace && pipelineError && (
          <div className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
            {pipelineError}
          </div>
        )}

        {workspace && pipelineLoading && (
          <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
            Loading pipeline assets…
          </div>
        )}

        {workspace && productSelected && !pipelineLoading && pipeline.length === 0 && !pipelineError && (
          <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
            No pipeline assets match this filter.
          </div>
        )}

        {workspace && pipeline.length > 0 && (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {pipeline.map((item) => {
              const media = buildMediaAsset(item);
              const creativeCount = item.meta?.creatives?.length || 0;
              const adCount = item.meta?.ads?.length || 0;
              const specStatus = item.creative_spec?.status || (item.creative_spec ? "ready" : "missing");
              const uploadStatus = item.meta?.upload?.status || (item.meta?.upload ? "uploaded" : "missing");
              const creativeStatus = creativeCount > 0 ? "ready" : "missing";
              const adStatus = adCount > 0 ? "ready" : "missing";

              return (
                <div key={item.asset.id} className="ds-card ds-card--md shadow-none space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="text-sm font-semibold text-content">
                        {item.campaign?.name || "Unlinked campaign"}
                      </div>
                      <div className="text-xs text-content-muted">
                        {item.experiment?.name || "No angle linked"}
                      </div>
                    </div>
                    <StatusBadge status={item.asset.status || "unknown"} />
                  </div>

                  <MediaTile asset={media} />

                  <div className="flex flex-wrap items-center gap-2 text-xs text-content-muted">
                    <span>Asset {shortId(item.asset.id, 4)}</span>
                    {item.asset.asset_kind ? <Badge tone="neutral">{item.asset.asset_kind}</Badge> : null}
                    {item.asset.width && item.asset.height ? (
                      <span>
                        {item.asset.width}×{item.asset.height}
                      </span>
                    ) : null}
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <PipelineStep label="Spec" status={specStatus} />
                    <PipelineStep label="Upload" status={uploadStatus} />
                    <PipelineStep label="Creative" status={creativeStatus} count={creativeCount} />
                    <PipelineStep label="Ad" status={adStatus} count={adCount} />
                  </div>

                  <div className="space-y-1 text-xs text-content-muted">
                    <div>
                      Meta campaign:{" "}
                      {item.meta?.meta_campaign?.meta_campaign_id
                        ? shortId(item.meta.meta_campaign.meta_campaign_id, 4)
                        : "—"}
                    </div>
                    <div>Updated: {formatDate(item.asset.created_at)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="ds-card ds-card--md shadow-none space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-content">Meta inventory (live)</div>
            <div className="text-xs text-content-muted">Direct read-only data from Meta.</div>
          </div>
          <div className="flex items-center gap-2 text-xs text-content-muted">
            {inventoryFetchedAt ? <span>Fetched {formatDate(inventoryFetchedAt)}</span> : null}
            <Button
              variant="secondary"
              size="xs"
              onClick={() => {
                if (!metaAdAccountId || !workspace?.id || !config?.id) return;
                setInventoryFetchedAt(null);
                setInventory(null);
                setInventoryError(null);
                setInventoryLoading(true);
                inventoryFetcher({
                  fetchAll: true,
                  clientId: workspace.id,
                  metaConfigId: config.id,
                  adAccountId: metaAdAccountId,
                })
                  .then((data) => {
                    setInventory(data);
                    setInventoryFetchedAt(new Date().toISOString());
                  })
                  .catch((err: ApiError) => {
                    setInventoryError(err?.message || "Failed to load Meta inventory");
                  })
                  .finally(() => setInventoryLoading(false));
              }}
              disabled={inventoryLoading || !metaAdAccountId || !workspace?.id || !config?.id}
            >
              {inventoryLoading ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {inventoryTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setInventoryTab(tab.key)}
                className={[
                  "rounded-full px-3 py-1.5 text-xs font-semibold transition",
                  inventoryTab === tab.key
                    ? "bg-primary text-primary-foreground"
                    : "bg-surface-2 text-content-muted hover:bg-hover",
                ].join(" ")}
              >
                {tab.label}
              </button>
          ))}
        </div>

        {inventoryError && (
          <div className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
            {inventoryError}
          </div>
        )}

        {metaConfigLoading && (
          <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
            Loading Meta config…
          </div>
        )}

        {configError && (
          <div className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
            {configError}
          </div>
        )}

        {inventoryLoading && (
          <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
            Loading Meta inventory…
          </div>
        )}

        {!inventoryLoading && inventory && (
          <Table variant="ghost">
            <TableHeader>
              <TableRow>
                {inventoryTab === "images" && (
                  <>
                    <TableHeadCell>Hash</TableHeadCell>
                    <TableHeadCell>Name</TableHeadCell>
                    <TableHeadCell>URL</TableHeadCell>
                    <TableHeadCell>Created</TableHeadCell>
                  </>
                )}
                {inventoryTab === "videos" && (
                  <>
                    <TableHeadCell>ID</TableHeadCell>
                    <TableHeadCell>Title</TableHeadCell>
                    <TableHeadCell>Status</TableHeadCell>
                    <TableHeadCell>Length</TableHeadCell>
                  </>
                )}
                {inventoryTab === "creatives" && (
                  <>
                    <TableHeadCell>ID</TableHeadCell>
                    <TableHeadCell>Name</TableHeadCell>
                    <TableHeadCell>Status</TableHeadCell>
                    <TableHeadCell>Updated</TableHeadCell>
                  </>
                )}
                {inventoryTab === "campaigns" && (
                  <>
                    <TableHeadCell>ID</TableHeadCell>
                    <TableHeadCell>Name</TableHeadCell>
                    <TableHeadCell>Status</TableHeadCell>
                    <TableHeadCell>Objective</TableHeadCell>
                  </>
                )}
                {inventoryTab === "adsets" && (
                  <>
                    <TableHeadCell>ID</TableHeadCell>
                    <TableHeadCell>Name</TableHeadCell>
                    <TableHeadCell>Status</TableHeadCell>
                    <TableHeadCell>Campaign</TableHeadCell>
                  </>
                )}
                {inventoryTab === "ads" && (
                  <>
                    <TableHeadCell>ID</TableHeadCell>
                    <TableHeadCell>Name</TableHeadCell>
                    <TableHeadCell>Status</TableHeadCell>
                    <TableHeadCell>Ad Set</TableHeadCell>
                  </>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {inventory.data.map((row: any) => {
                if (inventoryTab === "images") {
                  const item = row as MetaRemoteImage;
                  return (
                    <TableRow key={item.hash}>
                      <TableCell className="font-mono text-xs">{shortId(item.hash, 6)}</TableCell>
                      <TableCell>{item.name || "—"}</TableCell>
                      <TableCell className="truncate max-w-[240px]">{item.url || "—"}</TableCell>
                      <TableCell>{formatDate(item.created_time)}</TableCell>
                    </TableRow>
                  );
                }
                if (inventoryTab === "videos") {
                  const item = row as MetaRemoteVideo;
                  return (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
                      <TableCell>{item.title || "—"}</TableCell>
                      <TableCell>{item.status || "—"}</TableCell>
                      <TableCell>{item.length ? `${item.length}s` : "—"}</TableCell>
                    </TableRow>
                  );
                }
                if (inventoryTab === "creatives") {
                  const item = row as MetaRemoteCreative;
                  return (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
                      <TableCell>{item.name || "—"}</TableCell>
                      <TableCell>{item.status || "—"}</TableCell>
                      <TableCell>{formatDate(item.updated_time)}</TableCell>
                    </TableRow>
                  );
                }
                if (inventoryTab === "campaigns") {
                  const item = row as MetaRemoteCampaign;
                  return (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
                      <TableCell>{item.name || "—"}</TableCell>
                      <TableCell>{item.effective_status || item.status || "—"}</TableCell>
                      <TableCell>{item.objective || "—"}</TableCell>
                    </TableRow>
                  );
                }
                if (inventoryTab === "adsets") {
                  const item = row as MetaRemoteAdSet;
                  return (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
                      <TableCell>{item.name || "—"}</TableCell>
                      <TableCell>{item.effective_status || item.status || "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{shortId(item.campaign_id, 6)}</TableCell>
                    </TableRow>
                  );
                }
                const item = row as MetaRemoteAd;
                return (
                  <TableRow key={item.id}>
                    <TableCell className="font-mono text-xs">{shortId(item.id, 6)}</TableCell>
                    <TableCell>{item.name || "—"}</TableCell>
                    <TableCell>{item.effective_status || item.status || "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{shortId(item.adset_id, 6)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
