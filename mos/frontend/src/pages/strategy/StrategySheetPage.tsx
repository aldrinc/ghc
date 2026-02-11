import { useMemo } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { useLatestArtifact } from "@/api/artifacts";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import type { StrategySheet } from "@/types/artifacts";

export function StrategySheetPage() {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { latest: strategyArtifact, isLoading } = useLatestArtifact({
    clientId: workspace?.id,
    productId: product?.id,
    type: "strategy_sheet",
  });

  const strategy = useMemo(() => (strategyArtifact?.data || {}) as StrategySheet, [strategyArtifact?.data]);
  const channelPlan = strategy?.channelPlan || [];
  const messaging = strategy?.messaging || [];
  const risks = strategy?.risks || [];
  const mitigations = strategy?.mitigations || [];

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Strategy Sheet" description="Select a workspace to view strategy outputs." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm shadow-none">
          Choose a workspace from the sidebar.
        </div>
      </div>
    );
  }
  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Strategy Sheet" description="Select a product to view product-scoped strategy." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm shadow-none">
          Choose a product from the header to view strategy outputs.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Strategy Sheet"
        description={`Goal, hypothesis, channel plan, and messaging for ${product.name}.`}
      >
        {strategyArtifact ? (
          <div className="text-xs text-content-muted">Strategy sheets are auto-approved and do not require sign-off.</div>
        ) : null}
      </PageHeader>

      {isLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading strategy…</div>
      ) : !strategyArtifact ? (
        <div className="ds-card ds-card--md ds-card--empty text-sm shadow-none">
          No strategy sheet generated yet. Start campaign planning to populate this page.
        </div>
      ) : (
        <div className="space-y-4 ds-card ds-card--md shadow-none">
          <div>
            <div className="text-xs font-semibold text-content-muted uppercase">Goal</div>
            <div className="text-sm text-content mt-1">{strategy?.goal || "—"}</div>
          </div>
          <div>
            <div className="text-xs font-semibold text-content-muted uppercase">Hypothesis</div>
            <div className="text-sm text-content mt-1">{strategy?.hypothesis || "—"}</div>
          </div>

          <div>
            <div className="text-xs font-semibold text-content-muted uppercase mb-1">Channel plan</div>
            {channelPlan.length ? (
              <Table variant="ghost">
                <TableHeader>
                  <TableRow>
                    <TableHeadCell>Channel</TableHeadCell>
                    <TableHeadCell>Objective</TableHeadCell>
                    <TableHeadCell>Budget %</TableHeadCell>
                    <TableHeadCell>Notes</TableHeadCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {channelPlan.map((c, idx) => (
                    <TableRow key={`${c.channel}-${idx}`}>
                      <TableCell>{c.channel}</TableCell>
                      <TableCell className="text-xs text-content-muted">{c.objective || "—"}</TableCell>
                      <TableCell className="text-xs text-content-muted">
                        {c.budgetSplitPercent ?? "—"}
                      </TableCell>
                      <TableCell className="text-xs text-content-muted">{c.notes || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="text-xs text-content-muted">No channel plan generated.</div>
            )}
          </div>

          <div>
            <div className="text-xs font-semibold text-content-muted uppercase mb-1">Messaging</div>
            {messaging.length ? (
              <div className="grid gap-2 md:grid-cols-2">
                {messaging.map((m, idx) => (
                  <div key={`${m.title}-${idx}`} className="ds-card ds-card--sm bg-surface-2">
                    <div className="text-sm font-semibold text-content">{m.title}</div>
                    <div className="mt-1 text-xs text-content-muted">
                      Proof points: {(m.proofPoints || []).join(", ") || "—"}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-content-muted">No messaging pillars generated.</div>
            )}
          </div>

          <div className="grid gap-2 md:grid-cols-2">
            <div>
              <div className="text-xs font-semibold text-content-muted uppercase">Risks</div>
              <div className="mt-1 text-xs text-content-muted">
                {risks.length ? risks.map((r, i) => <div key={i}>• {r}</div>) : "—"}
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold text-content-muted uppercase">Mitigations</div>
              <div className="mt-1 text-xs text-content-muted">
                {mitigations.length ? mitigations.map((m, i) => <div key={i}>• {m}</div>) : "—"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
