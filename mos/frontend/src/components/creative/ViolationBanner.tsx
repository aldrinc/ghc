import { Badge } from "@/components/ui/badge";
import type { CardViolationSummary } from "@/types/creativeReview";

const severityTone = {
  blocker: "danger",
  high: "danger",
  medium: "accent",
  low: "neutral",
} as const;

const severityLabel = {
  blocker: "Blocker",
  high: "High",
  medium: "Medium",
  low: "Low",
} as const;

/**
 * Compact violation summary shown on each ad review card.
 * Shows the highest severity badge and total count.
 */
export function ViolationBanner({ violations }: { violations: CardViolationSummary }) {
  if (!violations.total || !violations.maxSeverity) return null;

  const tone = severityTone[violations.maxSeverity];
  const label = severityLabel[violations.maxSeverity];

  return (
    <div className="flex items-center gap-2">
      <Badge tone={tone}>{label}</Badge>
      <span className="text-xs text-content-muted">
        {violations.total} {violations.total === 1 ? "issue" : "issues"}
      </span>
    </div>
  );
}
