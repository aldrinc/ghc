import { useState } from "react";
import { CheckCircle2, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { readQueryError } from "./importUtils";
import {
  useApproveForPublish,
  useTemplateVariantDetail,
  useVariantGovernance,
} from "@/api/storefrontTemplates";

export function GovernancePanel({
  variantId,
  workspaceId,
  onApproved,
}: {
  variantId: string;
  workspaceId?: string;
  onApproved: () => void;
}) {
  const [showConfirm, setShowConfirm] = useState(false);

  const { data: governance, isLoading, error, refetch } = useVariantGovernance(variantId, workspaceId);
  const { data: variantDetail, refetch: refetchVariantDetail } = useTemplateVariantDetail(variantId, workspaceId);
  const approveForPublish = useApproveForPublish();

  const isAlreadyApproved = variantDetail?.status === "approved";

  const handleApprove = async () => {
    if (!workspaceId) return;
    try {
      await approveForPublish.mutateAsync({
        variantId,
        clientId: workspaceId,
      });
      setShowConfirm(false);
      onApproved();
      await Promise.all([refetch(), refetchVariantDetail()]);
    } catch (err) {
      console.error("Failed to approve variant:", err);
    }
  };

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-border bg-surface px-4 py-4">
        <div className="text-sm text-content-muted">Loading governance report...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-4">
        <div className="text-sm text-danger">
          {readQueryError(error, "Failed to load governance report.")}
        </div>
      </div>
    );
  }

  if (!governance) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <div className="text-sm font-semibold text-content">Governance</div>
          <div className="text-xs text-content-muted">
            Asset validation, style audit, and publish readiness.
          </div>
        </div>
        {isAlreadyApproved ? (
          <Badge tone="success">Approved</Badge>
        ) : (
          <Badge tone={governance.readyForPublish ? "success" : "warning"}>
            {governance.readyForPublish ? "Ready" : "Blocked"}
          </Badge>
        )}
      </div>

      {governance.blockers.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-danger">Blockers</div>
          {governance.blockers.map((blocker, idx) => (
            <div key={idx} className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
              {blocker}
            </div>
          ))}
        </div>
      )}

      {governance.warnings.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-warning">Warnings</div>
          {governance.warnings.map((warning, idx) => (
            <div key={idx} className="rounded-xl border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-content-muted">
              {warning}
            </div>
          ))}
        </div>
      )}

      {governance.assetValidations.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-content">Asset references</div>
          {governance.assetValidations.map((asset, idx) => (
            <div key={idx} className="rounded-xl border border-border bg-surface-2 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-content">{asset.publicId}</div>
                <Badge
                  tone={
                    asset.status === "approved"
                      ? "success"
                      : asset.status === "rejected"
                        ? "danger"
                        : asset.status === "pending"
                          ? "warning"
                          : "danger"
                  }
                >
                  {asset.status}
                </Badge>
              </div>
              {asset.blockType && (
                <div className="mt-1 text-xs text-content-muted">
                  {asset.blockType}{asset.blockId ? ` (${asset.blockId})` : ""}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {governance.styleAudit && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-content">Style audit</div>
            <Badge tone={governance.styleAudit.passed ? "success" : "danger"}>
              {governance.styleAudit.passed ? "Passed" : "Failed"}
            </Badge>
          </div>
          {governance.styleAudit.presetName && (
            <div className="text-xs text-content-muted">Preset: {governance.styleAudit.presetName}</div>
          )}
          {governance.styleAudit.findings.length > 0 && (
            <div className="space-y-1">
              {governance.styleAudit.findings.map((finding, idx) => (
                <div
                  key={idx}
                  className={cn(
                    "rounded-lg px-2 py-1 text-xs",
                    finding.status === "pass" ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
                  )}
                >
                  {finding.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {governance.puckDataStructure && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-content">PuckData structure</div>
            <Badge tone={governance.puckDataStructure.valid ? "success" : "danger"}>
              {governance.puckDataStructure.valid ? "Valid" : "Invalid"}
            </Badge>
          </div>
          {governance.puckDataStructure.errors.length > 0 && (
            <div className="space-y-1">
              {governance.puckDataStructure.errors.map((err, idx) => (
                <div key={idx} className="text-xs text-danger">{err}</div>
              ))}
            </div>
          )}
          {governance.puckDataStructure.warnings.length > 0 && (
            <div className="space-y-1">
              {governance.puckDataStructure.warnings.map((warn, idx) => (
                <div key={idx} className="text-xs text-warning">{warn}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {governance.provenanceEvents.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-content">Provenance</div>
          <div className="space-y-2">
            {governance.provenanceEvents.map((event, idx) => (
              <div key={idx} className="rounded-xl border border-border bg-surface-2 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-content">{event.eventType}</div>
                  <div className="text-xs text-content-muted">
                    {new Date(event.timestamp).toLocaleString()}
                  </div>
                </div>
                {event.actor && (
                  <div className="mt-1 text-xs text-content-muted">by {event.actor}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!isAlreadyApproved && governance.readyForPublish && (
        <div className="mt-4 space-y-3">
          {!showConfirm ? (
            <Button onClick={() => setShowConfirm(true)} className="w-full">
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Approve for Publish
            </Button>
          ) : (
            <>
              <div className="rounded-xl border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-content">
                Are you sure you want to approve this variant for publish?
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={handleApprove}
                  disabled={approveForPublish.isPending}
                  className="flex-1"
                >
                  {approveForPublish.isPending ? (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      Approving...
                    </>
                  ) : (
                    "Confirm Approval"
                  )}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowConfirm(false)}
                  disabled={approveForPublish.isPending}
                >
                  Cancel
                </Button>
              </div>
            </>
          )}
          {approveForPublish.isError && (
            <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
              Failed to approve variant. Please try again.
            </div>
          )}
        </div>
      )}

      {isAlreadyApproved && (
        <div className="mt-4 rounded-xl border border-success/30 bg-success/5 px-3 py-3 text-sm text-success">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>This variant has been approved for publish.</span>
          </div>
        </div>
      )}
    </div>
  );
}
