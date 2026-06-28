import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import { useClientFoundationReadiness } from "@/api/clients";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export function WorkspaceFoundationStatusPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { data: readiness, isLoading } = useClientFoundationReadiness(
    workspace?.id,
    product?.id,
    { enabled: Boolean(workspace?.id && product?.id), refetchIntervalMs: 15000 }
  );

  useEffect(() => {
    if (readiness?.status === "foundation_ready") {
      navigate("/workspaces/foundation-ready", { replace: true });
    }
  }, [navigate, readiness?.status]);

  if (!workspace || !product) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Foundation setup"
          description="Select a workspace and product to track foundational setup."
        />
        <EmptyState
          title="Workspace setup context missing"
          description="Choose a workspace and product first, then return here to continue setup tracking."
          actions={
            <Button variant="primary" size="sm" onClick={() => navigate("/workspaces")}>Go to workspaces</Button>
          }
        />
      </div>
    );
  }

  const isFailed = readiness?.status === "foundation_failed";
  const isPending = !readiness || readiness.status === "foundation_pending";

  return (
    <div className="space-y-4">
      <PageHeader
        title="Foundation setup"
        description="mOS will keep this workspace here until foundational docs are complete."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => navigate("/strategy")}>View workflow</Button>
            <Button variant="secondary" size="sm" onClick={() => navigate("/workspaces")}>Workspaces</Button>
          </div>
        }
      />

      <div className="ds-card ds-card--md space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">{workspace.name} · {product.title}</div>
            <div className="text-xs text-content-muted">Foundation readiness gate</div>
          </div>
          {isFailed ? (
            <Badge tone="danger">Setup blocked</Badge>
          ) : isPending ? (
            <Badge tone="accent">Setup running</Badge>
          ) : (
            <Badge tone="success">Ready</Badge>
          )}
        </div>

        <div className="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-content-muted">
          {isLoading ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Checking foundation status...
            </span>
          ) : isFailed ? (
            <span className="inline-flex items-start gap-2 text-danger">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              Foundation setup failed: {readiness?.reason || "unknown_error"}
            </span>
          ) : (
            <span className="inline-flex items-start gap-2">
              <Loader2 className="mt-0.5 h-4 w-4 animate-spin" />
              Foundation setup is still in progress. You will move forward automatically when ready.
            </span>
          )}
        </div>

        {readiness?.missing_step_keys?.length ? (
          <div className="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-content-muted">
            Missing foundational docs: {readiness.missing_step_keys.join(", ")}
          </div>
        ) : null}

        {isFailed ? (
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => readiness?.strategy_workflow_run_id && navigate(`/strategy/${readiness.strategy_workflow_run_id}`)}
              disabled={!readiness?.strategy_workflow_run_id}
            >
              Open failed run
            </Button>
          </div>
        ) : null}

        {!isFailed ? (
          <div className="text-xs text-content-muted">
            Last check: {readiness?.checked_at ? new Date(readiness.checked_at).toLocaleString() : "pending"}
          </div>
        ) : null}
      </div>
    </div>
  );
}
