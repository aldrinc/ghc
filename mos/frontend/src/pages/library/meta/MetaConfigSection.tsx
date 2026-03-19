import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/layout/EmptyState";
import { shortId, formatDate } from "@/lib/format";
import type { MetaWorkspaceAdConfig } from "@/types/meta";

export type MetaConfigSectionProps = {
  hasWorkspace: boolean;
  config: MetaWorkspaceAdConfig | null;
  workspaceConfigs: MetaWorkspaceAdConfig[];
  configError: string | null;
  configPending: boolean;
  setupError: string | null;
  onSelectConfig: (configId: string) => void;
  onValidateActiveConfig: () => void;
};

export function MetaConfigSection({
  hasWorkspace,
  config,
  workspaceConfigs,
  configError,
  configPending,
  setupError,
  onSelectConfig,
  onValidateActiveConfig,
}: MetaConfigSectionProps) {
  return (
    <div className="ds-card ds-card--md shadow-none space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-content">Meta integration</div>
          <div className="text-xs text-content-muted">
            Connect org-wide Meta ad accounts once, then attach and select them per workspace.
          </div>
        </div>
        {hasWorkspace && config ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={onValidateActiveConfig}
            disabled={configPending}
          >
            {configPending ? "Refreshing…" : "Refresh workspace config from Meta"}
          </Button>
        ) : null}
      </div>

      {hasWorkspace && workspaceConfigs.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-[minmax(0,320px),1fr]">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-content">Active workspace Meta config</label>
            <Select
              value={config?.id || ""}
              onValueChange={onSelectConfig}
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
                {config.pixelId ? <Badge tone="neutral">Pixel {shortId(config.pixelId, 4)}</Badge> : null}
                <Badge tone="neutral">{config.connection.graphApiVersion}</Badge>
                <Badge tone={config.validationStatus === "valid" ? "success" : "neutral"}>
                  {config.validationStatus}
                </Badge>
                <span>Last synced: {formatDate(config.lastValidatedAt)}</span>
              </>
            ) : configError ? (
              <span className="text-danger">{configError}</span>
            ) : (
              <span>Loading Meta config…</span>
            )}
          </div>
        </div>
      ) : hasWorkspace ? (
        <EmptyState description={configError || "No Meta configs are attached to this workspace yet."} />
      ) : (
        <EmptyState description="Select a workspace to manage Meta setup." />
      )}

      {setupError ? (
        <Callout variant="danger" size="sm">
          {setupError}
        </Callout>
      ) : null}
    </div>
  );
}
