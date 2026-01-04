import { useMemo } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLatestArtifact } from "@/api/artifacts";
import type { AssetBrief, ExperimentSpec } from "@/types/artifacts";

export function ExperimentsPage() {
  const { workspace } = useWorkspace();
  const { latest: experimentArtifact, isLoading } = useLatestArtifact({
    clientId: workspace?.id,
    type: "experiment_spec",
  });
  const { latest: briefsArtifact, isLoading: briefsLoading } = useLatestArtifact({
    clientId: workspace?.id,
    type: "asset_brief",
  });

  const experiments = useMemo(() => {
    const data = (experimentArtifact?.data || {}) as { experimentSpecs?: ExperimentSpec[]; experiment_specs?: ExperimentSpec[] };
    return data.experimentSpecs || (data as any).experiment_specs || [];
  }, [experimentArtifact?.data]);

  const briefs = useMemo(() => {
    const data = (briefsArtifact?.data || {}) as { asset_briefs?: AssetBrief[] };
    return data.asset_briefs || [];
  }, [briefsArtifact?.data]);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Experiments" description="Select a workspace to view experiments." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a workspace from the sidebar.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Experiments" description="Generated experiment plans and related asset briefs." />

      {isLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading experiments…</div>
      ) : experiments.length ? (
        <div className="ds-card ds-card--md p-0">
          <div className="border-b border-border px-4 py-3">
            <div className="text-sm font-semibold text-content">Experiment specs</div>
            <div className="text-xs text-content-muted">Generated from the latest strategy sheet.</div>
          </div>
          <div className="divide-y divide-border">
            {experiments.map((exp) => (
              <div key={exp.id} className="px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-content">{exp.name}</div>
                  <div className="text-xs text-content-muted font-mono">{exp.id}</div>
                </div>
                <div className="mt-1 text-xs text-content-muted">{exp.hypothesis || "No hypothesis set."}</div>
                <div className="mt-2 text-xs text-content-muted">
                  Metrics: {(exp.metricIds || []).join(", ") || "—"} · Variants: {(exp.variants || []).length}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          No experiments generated yet. Approve strategy to trigger experiment planning.
        </div>
      )}

      {briefsLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading briefs…</div>
      ) : briefs.length ? (
        <div className="ds-card ds-card--md p-0">
          <div className="border-b border-border px-4 py-3">
            <div className="text-sm font-semibold text-content">Asset briefs</div>
            <div className="text-xs text-content-muted">Requirements derived from experiment variants.</div>
          </div>
          <div className="divide-y divide-border">
            {briefs.map((brief) => (
              <div key={brief.id} className="px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-content">{brief.creativeConcept || brief.id}</div>
                  <div className="text-xs text-content-muted font-mono">{brief.id}</div>
                </div>
                <div className="mt-1 text-xs text-content-muted">
                  Experiment: {brief.experimentId || "—"} · Requirements: {(brief.requirements || []).length}
                </div>
                {brief.requirements?.length ? (
                  <div className="mt-2 grid gap-1 text-xs text-content-muted">
                    {brief.requirements.map((req, idx) => (
                      <div key={`${brief.id}-req-${idx}`}>
                        • {req.channel} / {req.format} {req.angle ? `– ${req.angle}` : ""} {req.hook ? `(${req.hook})` : ""}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          Asset briefs will appear after experiments are generated.
        </div>
      )}
    </div>
  );
}
