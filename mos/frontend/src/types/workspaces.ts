export type WorkspaceStatus = "active" | "paused" | "archived";

export interface Workspace {
  id: string;
  name: string;
  industry?: string;
  lastActive?: string;
  status?: WorkspaceStatus;
}
