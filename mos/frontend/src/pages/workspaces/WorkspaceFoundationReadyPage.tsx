import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";

import { useClientFoundationReadiness } from "@/api/clients";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { Button } from "@/components/ui/button";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export function WorkspaceFoundationReadyPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { data: readiness } = useClientFoundationReadiness(
    workspace?.id,
    product?.id,
    { enabled: Boolean(workspace?.id && product?.id), refetchIntervalMs: 15000 }
  );

  useEffect(() => {
    if (readiness && readiness.status !== "foundation_ready" && readiness.should_gate_overview) {
      navigate("/workspaces/foundation-status", { replace: true });
    }
  }, [navigate, readiness]);

  if (!workspace || !product) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Foundation ready"
          description="Select a workspace and product to continue."
        />
        <EmptyState
          title="Workspace context missing"
          description="Choose a workspace and product first."
          actions={
            <Button variant="primary" size="sm" onClick={() => navigate("/workspaces")}>Go to workspaces</Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Foundation complete"
        description="Your workspace has the foundational docs needed to start execution."
      />

      <div className="ds-card ds-card--md space-y-4">
        <div className="flex items-start gap-3 rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-success">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <div className="text-sm font-semibold">{workspace.name} · {product.title} is ready</div>
            <div className="text-sm">Foundation research and docs are complete. Continue into workspace overview.</div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="primary" size="sm" onClick={() => navigate("/workspaces/overview")}>Continue to overview</Button>
          <Button variant="secondary" size="sm" onClick={() => navigate("/strategy")}>View strategy runs</Button>
        </div>
      </div>
    </div>
  );
}
