import { CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type StrategyCompleteSummaryProps = {
  selectedAngleName: string;
  selectedUmpName?: string;
  selectedUmsName?: string;
  selectedVariantName?: string;
  copyApproved: boolean;
  onLaunchClick: () => void;
  hasLaunches: boolean;
};

export function StrategyCompleteSummary({
  selectedAngleName,
  selectedUmpName,
  selectedUmsName,
  selectedVariantName,
  copyApproved,
  onLaunchClick,
  hasLaunches,
}: StrategyCompleteSummaryProps) {
  return (
    <div className="ds-card space-y-5">
      {/* Header */}
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 size-6 shrink-0 text-success" />
        <div className="min-w-0">
          <h3 className="text-base font-semibold leading-tight text-content">
            Strategy review complete
          </h3>
          <p className="mt-1 text-sm text-content-muted">
            You selected <strong>{selectedAngleName}</strong> as your angle,{" "}
            <strong>
              {selectedUmpName || "\u2014"} / {selectedUmsName || "\u2014"}
            </strong>{" "}
            as your messaging, and approved the final copy.
          </p>
        </div>
      </div>

      {/* 2x2 summary grid */}
      <div className="grid grid-cols-2 gap-3">
        <SummaryItem label="Angle" value={selectedAngleName || "\u2014"} />
        <SummaryItem
          label="Messaging"
          value={`${selectedUmpName || "\u2014"} / ${selectedUmsName || "\u2014"}`}
        />
        <SummaryItem label="Offer" value={selectedVariantName || "\u2014"} />
        <div className="rounded-md border border-border bg-surface-2/50 px-3 py-2">
          <p className="text-xs text-content-muted">Copy</p>
          <div className="mt-1">
            {copyApproved ? (
              <Badge tone="success">Approved</Badge>
            ) : (
              <Badge tone="danger">Rejected</Badge>
            )}
          </div>
        </div>
      </div>

      {/* CTA */}
      <Button variant="primary" className="w-full" onClick={onLaunchClick}>
        {hasLaunches ? "Launch more angles \u2192" : "Launch your first campaign \u2192"}
      </Button>
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-surface-2/50 px-3 py-2">
      <p className="text-xs text-content-muted">{label}</p>
      <p className="mt-0.5 truncate text-sm font-medium text-content">{value}</p>
    </div>
  );
}
