import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { requirementTone } from "./importUtils";
import type { StorefrontBindingPreviewRequirement } from "@/types/storefrontTemplates";

export function RequirementRow({ requirement }: { requirement: StorefrontBindingPreviewRequirement }) {
  const tone = requirementTone(requirement.status);
  const icon =
    tone === "success" ? (
      <CheckCircle2 className="h-4 w-4 text-success" />
    ) : (
      <AlertTriangle className={cn("h-4 w-4", tone === "danger" ? "text-danger" : "text-warning")} />
    );

  return (
    <div className="rounded-xl border border-border bg-surface-2 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 shrink-0">{icon}</div>
          <div>
            <div className="text-sm font-semibold text-content">{requirement.label}</div>
            <div className="mt-1 text-xs text-content-muted">{requirement.detail}</div>
          </div>
        </div>
        <Badge tone={tone}>{requirement.status}</Badge>
      </div>
    </div>
  );
}
