import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FieldRoot, FieldLabel } from "@/components/ui/field";
import type { ConnectionFormState } from "@/hooks/useMetaConfig";

export type ConnectAccountFormProps = {
  formState: ConnectionFormState;
  onFieldChange: <K extends keyof ConnectionFormState>(field: K, value: ConnectionFormState[K]) => void;
  onSubmit: () => void;
  disabled: boolean;
};

export function ConnectAccountForm({ formState, onFieldChange, onSubmit, disabled }: ConnectAccountFormProps) {
  const canSubmit = formState.accessToken.trim() !== "";

  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface p-4">
      <div>
        <div className="text-sm font-semibold text-content">Connect new ad account</div>
        <div className="text-xs text-content-muted">
          Credentials live on the reusable connection. Page and pixel stay on the workspace config.
        </div>
      </div>

      <FieldRoot>
        <FieldLabel className="text-xs">Connection name</FieldLabel>
        <Input
          value={formState.connectionName}
          onChange={(e) => onFieldChange("connectionName", e.target.value)}
          placeholder="e.g. My Brand"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">Ad account ID</FieldLabel>
        <Input
          value={formState.adAccountId}
          onChange={(e) => onFieldChange("adAccountId", e.target.value)}
          placeholder="Optional: act_123456789"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">Ad account name</FieldLabel>
        <Input
          value={formState.adAccountName}
          onChange={(e) => onFieldChange("adAccountName", e.target.value)}
          placeholder="Ad account name"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">
          Access token <span className="text-danger">*</span>
        </FieldLabel>
        <Input
          type="password"
          value={formState.accessToken}
          onChange={(e) => onFieldChange("accessToken", e.target.value)}
          placeholder="Paste access token"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">Graph API version</FieldLabel>
        <Input
          value={formState.graphApiVersion}
          onChange={(e) => onFieldChange("graphApiVersion", e.target.value)}
          placeholder="v24.0"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">Workspace config name</FieldLabel>
        <Input
          value={formState.workspaceConfigName}
          onChange={(e) => onFieldChange("workspaceConfigName", e.target.value)}
          placeholder="Workspace config name"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">Page ID</FieldLabel>
        <Input
          value={formState.pageId}
          onChange={(e) => onFieldChange("pageId", e.target.value)}
          placeholder="Page ID"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">Pixel ID</FieldLabel>
        <Input
          value={formState.pixelId}
          onChange={(e) => onFieldChange("pixelId", e.target.value)}
          placeholder="Pixel ID"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">Verified domain</FieldLabel>
        <Input
          value={formState.verifiedDomain}
          onChange={(e) => onFieldChange("verifiedDomain", e.target.value)}
          placeholder="example.com"
        />
      </FieldRoot>

      <FieldRoot>
        <FieldLabel className="text-xs">Tracking URL parameters</FieldLabel>
        <Input
          value={formState.trackingParams}
          onChange={(e) => onFieldChange("trackingParams", e.target.value)}
          placeholder="utm_source=meta&utm_medium=paid"
        />
      </FieldRoot>

      <Button
        type="button"
        variant="primary"
        size="sm"
        onClick={onSubmit}
        disabled={disabled || !canSubmit}
      >
        {disabled ? "Saving…" : "Connect and attach"}
      </Button>
    </div>
  );
}
