import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useClients } from "@/api/clients";
import type { Client } from "@/types/common";
import type { Workspace } from "@/types/workspaces";
import { clearActiveWorkspace, loadActiveWorkspace, saveActiveWorkspace } from "@/lib/workspaces";

type WorkspaceContextValue = {
  workspace: Workspace | null;
  selectWorkspace: (clientId: string, fallback?: Partial<Workspace>) => void;
  clearWorkspace: () => void;
  clients: Client[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
};

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { data: clients = [], isLoading, refetch, error, isError } = useClients();
  const [workspace, setWorkspace] = useState<Workspace | null>(() => loadActiveWorkspace());

  useEffect(() => {
    if (!clients.length || !workspace) return;
    const exists = clients.some((client) => client.id === workspace.id);
    if (!exists) {
      setWorkspace(null);
      clearActiveWorkspace();
    }
  }, [clients, workspace]);

  const selectWorkspace = useCallback(
    (clientId: string, fallback?: Partial<Workspace>) => {
      const client = clients.find((c) => c.id === clientId);
      const ws: Workspace | null = client
        ? { id: client.id, name: client.name, industry: client.industry }
        : fallback
        ? { id: clientId, name: fallback.name || "Workspace", industry: fallback.industry }
        : null;
      if (!ws) return;
      setWorkspace(ws);
      saveActiveWorkspace(ws);
    },
    [clients]
  );

  const clearWorkspace = useCallback(() => {
    setWorkspace(null);
    clearActiveWorkspace();
  }, []);

  const value = useMemo(
    () => ({
      workspace,
      selectWorkspace,
      clearWorkspace,
      clients,
      isLoading,
      isError,
      error,
      refetch,
    }),
    [workspace, selectWorkspace, clearWorkspace, clients, isLoading, isError, error, refetch]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return ctx;
}
