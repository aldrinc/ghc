import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/layout/EmptyState";
import { shortId } from "@/lib/format";
import type { MetaAdAccountConnection, MetaWorkspaceAdConfig } from "@/types/meta";

export type ConnectionsTableProps = {
  connections: MetaAdAccountConnection[];
  workspaceConfigs: MetaWorkspaceAdConfig[];
  workspaceId: string;
  connectionAccessTokens: Record<string, string>;
  onAccessTokenChange: (connectionId: string, value: string) => void;
  onValidate: (connectionId: string) => void;
  onAttach: (connection: MetaAdAccountConnection) => void;
  onUpdateCredentials: (connection: MetaAdAccountConnection) => void;
  disabled: boolean;
};

export function ConnectionsTable({
  connections,
  workspaceConfigs,
  workspaceId,
  connectionAccessTokens,
  onAccessTokenChange,
  onValidate,
  onAttach,
  onUpdateCredentials,
  disabled,
}: ConnectionsTableProps) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface p-4">
      <div>
        <div className="text-sm font-semibold text-content">Org-connected ad accounts</div>
        <div className="text-xs text-content-muted">
          Reuse an existing Meta ad account across workspaces without re-entering credentials.
        </div>
      </div>

      {connections.length === 0 ? (
        <EmptyState
          title="No ad accounts"
          description="Connect a Meta ad account to get started."
        />
      ) : (
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
              const attachedToWorkspace = workspaceConfigs.some(
                (entry) => entry.connectionId === connection.id,
              );
              return (
                <TableRow key={connection.id}>
                  <TableCell>
                    <div className="space-y-1">
                      <div className="text-sm font-semibold text-content">{connection.name}</div>
                      <div className="text-xs text-content-muted">
                        {connection.adAccountName || shortId(connection.adAccountId, 4)} ·{" "}
                        {connection.graphApiVersion}
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
                            type="password"
                            value={connectionAccessTokens[connection.id] || ""}
                            onChange={(e) => onAccessTokenChange(connection.id, e.target.value)}
                            placeholder="Paste access token to reconnect"
                            className="h-8 min-w-[220px] max-w-[360px]"
                          />
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            onClick={() => onUpdateCredentials(connection)}
                            disabled={disabled || !(connectionAccessTokens[connection.id] || "").trim()}
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
                          <Badge
                            key={usage.configId}
                            tone={usage.clientId === workspaceId ? "accent" : "neutral"}
                          >
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
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => onValidate(connection.id)}
                        disabled={disabled}
                      >
                        Validate
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => onAttach(connection)}
                        disabled={disabled || attachedToWorkspace}
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
      )}
    </div>
  );
}
