import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { useCampaignContext } from "@/contexts/CampaignContext";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function truncate(text?: string, max = 120) {
  if (!text) return "—";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

const READABILITY_MAX_WIDTH_CLASS = "w-full max-w-4xl";

export function CampaignStrategyTab() {
  const { strategyArtifact, strategyLoading, strategy } = useCampaignContext();

  const channelPlan = strategy.channelPlan || [];
  const messaging = strategy.messaging || [];
  const risks = strategy.risks || [];
  const mitigations = strategy.mitigations || [];

  return (
    <div className={READABILITY_MAX_WIDTH_CLASS}>
      {strategyLoading ? (
        <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
          Loading strategy sheet…
        </div>
      ) : !strategyArtifact ? (
        <div className="border border-border bg-transparent px-4 py-3 text-base">
          No strategy sheet generated yet.
        </div>
      ) : (
        <div className="space-y-4">
          <div className="border border-border bg-transparent p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-base font-semibold text-content">Strategy sheet</div>
                <div className="text-sm text-content-muted">
                  Updated {formatDate(strategyArtifact.created_at)}
                </div>
              </div>
            </div>
            <div className="mt-2 text-sm text-content-muted">Strategy sheets are auto-approved.</div>
            <div className="mt-4 space-y-3 text-base text-content">
              <div>
                <div className="text-sm font-semibold text-content-muted uppercase">Goal</div>
                <div>{truncate(strategy.goal || "—", 240)}</div>
              </div>
              <div>
                <div className="text-sm font-semibold text-content-muted uppercase">Hypothesis</div>
                <div>{truncate(strategy.hypothesis || "—", 240)}</div>
              </div>
            </div>
          </div>

          <div className="border border-border bg-transparent">
            <div className="border-b border-border px-4 py-3">
              <div className="text-base font-semibold text-content">Channel plan</div>
              <div className="text-sm text-content-muted">Budget split and objectives by channel.</div>
            </div>
            <div className="p-4">
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
                    {channelPlan.map((plan, idx) => (
                      <TableRow key={`${plan.channel}-${idx}`}>
                        <TableCell>{plan.channel}</TableCell>
                        <TableCell className="text-sm text-content-muted">
                          {truncate(plan.objective, 120)}
                        </TableCell>
                        <TableCell className="text-sm text-content-muted">
                          {plan.budgetSplitPercent ?? "—"}
                        </TableCell>
                        <TableCell className="text-sm text-content-muted">{truncate(plan.notes, 120)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="text-sm text-content-muted">No channel plan generated yet.</div>
              )}
            </div>
          </div>

          <div className="border border-border bg-transparent">
            <div className="border-b border-border px-4 py-3">
              <div className="text-base font-semibold text-content">Messaging</div>
              <div className="text-sm text-content-muted">Proof points and story arcs.</div>
            </div>
            <div className="p-4">
              {messaging.length ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {messaging.map((msg, idx) => (
                    <div key={`${msg.title}-${idx}`} className="border border-border bg-transparent p-3">
                      <div className="text-base font-semibold text-content">
                        {msg.title || "Messaging pillar"}
                      </div>
                      <div className="mt-1 text-sm text-content-muted">
                        Proof points: {(msg.proofPoints || []).join("; ") || "—"}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-content-muted">No messaging pillars generated yet.</div>
              )}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="border border-border bg-transparent p-4">
              <div className="text-base font-semibold text-content">Risks</div>
              <div className="mt-2 text-sm text-content-muted">
                {risks.length ? risks.map((risk, idx) => <div key={`risk-${idx}`}>• {risk}</div>) : "—"}
              </div>
            </div>
            <div className="border border-border bg-transparent p-4">
              <div className="text-base font-semibold text-content">Mitigations</div>
              <div className="mt-2 text-sm text-content-muted">
                {mitigations.length
                  ? mitigations.map((risk, idx) => <div key={`mitigation-${idx}`}>• {risk}</div>)
                  : "—"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
