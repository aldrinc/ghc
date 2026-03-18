import { useEffect, useState } from "react";
import { useMetaApi } from "@/api/meta";
import { Badge } from "@/components/ui/badge";
import type { MetaPublishRun } from "@/types/meta";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const statusTone: Record<string, "neutral" | "accent" | "success" | "danger"> = {
  completed: "success",
  running: "accent",
  failed: "danger",
  pending: "neutral",
};

/**
 * Lists Meta publish runs for a campaign.
 */
export function MetaPublishRunsList({ campaignId }: { campaignId: string }) {
  const metaApi = useMetaApi();
  const [runs, setRuns] = useState<MetaPublishRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    metaApi.listPublishRuns(campaignId).then((data) => {
      if (!cancelled) {
        setRuns(data);
        setLoading(false);
      }
    }).catch(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [campaignId, metaApi]);

  if (loading) {
    return <div className="text-sm text-content-muted">Loading publish runs…</div>;
  }

  if (!runs.length) {
    return <div className="text-sm text-content-muted">No publish runs yet.</div>;
  }

  return (
    <div className="space-y-2">
      {runs.map((run) => (
        <div key={run.id} className="flex items-center gap-3 rounded-lg border border-border px-4 py-3">
          <Badge tone={statusTone[run.status] || "neutral"}>{run.status}</Badge>
          <span className="text-xs font-mono text-content-muted">{run.id.slice(0, 8)}</span>
          <span className="text-xs text-content-muted">{formatDate(run.createdAt)}</span>
          {run.items.length > 0 ? (
            <span className="text-xs text-content-muted">{run.items.length} ads</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
