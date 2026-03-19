import { useCallback, useEffect, useState } from "react";
import { useMetaApi } from "@/api/meta";
import type { ApiError } from "@/api/client";
import type { MetaAdAccountConnection, MetaWorkspaceAdConfig } from "@/types/meta";

export type ConnectionFormState = {
  connectionName: string;
  adAccountId: string;
  adAccountName: string;
  accessToken: string;
  graphApiVersion: string;
  workspaceConfigName: string;
  pageId: string;
  pixelId: string;
  verifiedDomain: string;
  trackingParams: string;
};

const INITIAL_FORM: ConnectionFormState = {
  connectionName: "",
  adAccountId: "",
  adAccountName: "",
  accessToken: "",
  graphApiVersion: "v24.0",
  workspaceConfigName: "",
  pageId: "",
  pixelId: "",
  verifiedDomain: "",
  trackingParams: "utm_source=meta&utm_medium=paid",
};

export function useMetaConfig(workspaceId: string | undefined) {
  const {
    createConnection,
    createWorkspaceConfig,
    getActiveConfig,
    listConnections,
    listWorkspaceConfigs,
    selectWorkspaceConfig,
    updateConnection,
    validateConnection,
    validateWorkspaceConfig,
  } = useMetaApi();

  const [config, setConfig] = useState<MetaWorkspaceAdConfig | null>(null);
  const [workspaceConfigs, setWorkspaceConfigs] = useState<MetaWorkspaceAdConfig[]>([]);
  const [connections, setConnections] = useState<MetaAdAccountConnection[]>([]);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configPending, setConfigPending] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const [setupPending, setSetupPending] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [formState, setFormState] = useState<ConnectionFormState>(INITIAL_FORM);
  const [connectionAccessTokens, setConnectionAccessTokens] = useState<Record<string, string>>({});

  const setFormField = useCallback(<K extends keyof ConnectionFormState>(field: K, value: ConnectionFormState[K]) => {
    setFormState((prev) => ({ ...prev, [field]: value }));
  }, []);

  const resetForm = useCallback(() => setFormState(INITIAL_FORM), []);

  const refreshMetaState = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const [connectionRows, workspaceConfigRows] = await Promise.all([
        listConnections(),
        listWorkspaceConfigs(workspaceId),
      ]);
      setConnections(connectionRows);
      setWorkspaceConfigs(workspaceConfigRows);
      try {
        const active = await getActiveConfig(workspaceId);
        setConfig(active);
        setConfigError(null);
      } catch (err) {
        setConfig(null);
        setConfigError((err as ApiError)?.message || "No active Meta config selected for this workspace");
      }
    } catch (err) {
      setConnections([]);
      setWorkspaceConfigs([]);
      setConfig(null);
      setConfigError((err as ApiError)?.message || "Failed to load Meta setup");
    }
  }, [getActiveConfig, listConnections, listWorkspaceConfigs, workspaceId]);

  // Initial load
  useEffect(() => {
    if (!workspaceId) {
      setConfig(null);
      setWorkspaceConfigs([]);
      setConnections([]);
      setConfigError(null);
      setConfigLoading(false);
      return;
    }
    let cancelled = false;
    setConfigLoading(true);

    (async () => {
      try {
        const [connectionRows, workspaceConfigRows] = await Promise.all([
          listConnections(),
          listWorkspaceConfigs(workspaceId),
        ]);
        if (cancelled) return;
        setConnections(connectionRows);
        setWorkspaceConfigs(workspaceConfigRows);
        try {
          const active = await getActiveConfig(workspaceId);
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
      } finally {
        if (!cancelled) setConfigLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [getActiveConfig, listConnections, listWorkspaceConfigs, workspaceId]);

  const handleSelectWorkspaceConfig = useCallback(
    async (configId: string) => {
      if (!workspaceId || !configId) return;
      setConfigPending(true);
      setConfigError(null);
      try {
        const active = await selectWorkspaceConfig(workspaceId, configId);
        setConfig(active);
        setWorkspaceConfigs((current) =>
          current.map((entry) => ({ ...entry, isDefault: entry.id === active.id })),
        );
      } catch (err) {
        setConfigError((err as ApiError)?.message || "Failed to activate workspace Meta config");
      } finally {
        setConfigPending(false);
      }
    },
    [selectWorkspaceConfig, workspaceId],
  );

  const handleCreateAndAttachConnection = useCallback(async () => {
    if (!workspaceId) return;
    setSetupPending(true);
    setSetupError(null);
    try {
      const connection = await createConnection({
        name: formState.connectionName.trim() || formState.adAccountName.trim() || "Meta connection",
        adAccountId: formState.adAccountId.trim() || undefined,
        adAccountName: formState.adAccountName.trim() || undefined,
        accessToken: formState.accessToken.trim(),
        graphApiVersion: formState.graphApiVersion.trim() || "v24.0",
        graphApiBaseUrl: "https://graph.facebook.com",
        status: "active",
        metadata: {},
      });
      await createWorkspaceConfig(workspaceId, {
        connectionId: connection.id,
        name: formState.workspaceConfigName.trim() || formState.connectionName.trim() || "Meta workspace config",
        isDefault: workspaceConfigs.length === 0,
        pageId: formState.pageId.trim() || undefined,
        pixelId: formState.pixelId.trim() || undefined,
        verifiedDomain: formState.verifiedDomain.trim() || undefined,
        trackingUrlParameters: formState.trackingParams.trim() || undefined,
        status: "active",
        metadata: {},
      });
      resetForm();
      await refreshMetaState();
    } catch (err) {
      setSetupError((err as ApiError)?.message || "Failed to create Meta connection");
    } finally {
      setSetupPending(false);
    }
  }, [createConnection, createWorkspaceConfig, formState, refreshMetaState, resetForm, workspaceConfigs.length, workspaceId]);

  const handleAttachExistingConnection = useCallback(
    async (connection: MetaAdAccountConnection) => {
      if (!workspaceId) return;
      setSetupPending(true);
      setSetupError(null);
      try {
        await createWorkspaceConfig(workspaceId, {
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
    },
    [createWorkspaceConfig, refreshMetaState, workspaceConfigs.length, workspaceId],
  );

  const handleValidateConnection = useCallback(
    async (connectionId: string) => {
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
    },
    [refreshMetaState, validateConnection],
  );

  const handleUpdateConnectionCredentials = useCallback(
    async (connection: MetaAdAccountConnection) => {
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
        setConnectionAccessTokens((current) => ({ ...current, [connection.id]: "" }));
        await refreshMetaState();
      } catch (err) {
        setSetupError((err as ApiError)?.message || "Failed to update Meta connection credentials");
      } finally {
        setSetupPending(false);
      }
    },
    [connectionAccessTokens, refreshMetaState, updateConnection],
  );

  const handleValidateActiveWorkspaceConfig = useCallback(async () => {
    if (!workspaceId || !config?.id) return;
    setConfigPending(true);
    setConfigError(null);
    try {
      const validated = await validateWorkspaceConfig(workspaceId, config.id);
      setConfig(validated);
      setWorkspaceConfigs((current) =>
        current.map((entry) => (entry.id === validated.id ? validated : entry)),
      );
    } catch (err) {
      setConfigError((err as ApiError)?.message || "Failed to validate active Meta workspace config");
    } finally {
      setConfigPending(false);
    }
  }, [config?.id, validateWorkspaceConfig, workspaceId]);

  const setConnectionAccessToken = useCallback((connectionId: string, value: string) => {
    setConnectionAccessTokens((current) => ({ ...current, [connectionId]: value }));
  }, []);

  return {
    config,
    workspaceConfigs,
    connections,
    configError,
    configPending,
    configLoading,
    setupPending,
    setupError,
    formState,
    setFormField,
    resetForm,
    connectionAccessTokens,
    setConnectionAccessToken,
    refreshMetaState,
    handleSelectWorkspaceConfig,
    handleCreateAndAttachConnection,
    handleAttachExistingConnection,
    handleValidateConnection,
    handleUpdateConnectionCredentials,
    handleValidateActiveWorkspaceConfig,
  };
}
