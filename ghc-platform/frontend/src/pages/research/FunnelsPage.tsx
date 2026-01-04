import { PageHeader } from "@/components/layout/PageHeader";

export function FunnelsPage() {
  return (
    <div className="space-y-4">
      <PageHeader title="Funnels" description="Funnel breakdowns will appear here once data is available." />
      <div className="ds-card ds-card--md ds-card--empty text-content-muted text-sm">
        No funnel data yet. Generate workflows to populate this view when funnel outputs are ready.
      </div>
    </div>
  );
}
