import { useState } from "react";

import type { StrategySkillsStatus } from "@/api/productStrategySkills";
import type { useApproveFoundationalStrategySkills } from "@/api/productStrategySkills";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";

type FoundationalStepProps = {
  isActive: boolean;
  isCompleted: boolean;
  completeness: StrategySkillsStatus["foundationalCompleteness"];
  legacyMetadataMissing: boolean;
  approveFoundational: ReturnType<typeof useApproveFoundationalStrategySkills>;
};

export function FoundationalStep({
  isActive,
  isCompleted,
  completeness,
  legacyMetadataMissing,
  approveFoundational,
}: FoundationalStepProps) {
  const [allowIncomplete, setAllowIncomplete] = useState(false);

  if (isCompleted) {
    return (
      <details className="ds-card ds-card--sm shadow-none">
        <summary className="flex cursor-pointer items-center gap-2 px-4 py-3">
          <span className="text-sm font-semibold text-content">Approve Foundational</span>
          <span className="text-xs text-success">Approved</span>
        </summary>
        <div className="border-t border-border px-4 py-3 text-sm text-content-muted">
          {completeness ? (
            <span>
              {completeness.presentDocKeys.length} of {completeness.expectedDocKeys.length} docs imported.
            </span>
          ) : (
            "Foundational bundle approved."
          )}
        </div>
      </details>
    );
  }

  if (!isActive) {
    return (
      <div className="ds-card ds-card--sm opacity-50 shadow-none">
        <div className="px-4 py-3">
          <div className="text-sm font-semibold text-content-muted">Approve Foundational</div>
          <div className="mt-1 text-xs text-content-muted">
            Review foundational doc completeness and approve to seed working bundles.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ds-card ds-card--sm ring-1 ring-accent/20 shadow-none" id="step-foundational">
      <div className="px-4 py-3">
        <div className="text-sm font-semibold text-content">Approve Foundational Bundle</div>
        <div className="mt-1 text-xs text-content-muted">
          Review the imported source docs, then approve to create the initial working and approved bundles.
        </div>
      </div>
      <div className="border-t border-border px-4 py-4">
        {completeness ? (
          <Callout
            variant={completeness.isComplete ? "success" : "warning"}
            title="Document completeness"
          >
            <div className="space-y-1">
              <div>Expected: {completeness.expectedDocKeys.length}</div>
              <div>Present: {completeness.presentDocKeys.length}</div>
              <div>Missing: {completeness.missingDocKeys.length}</div>
              {legacyMetadataMissing ? (
                <div className="mt-2">
                  This foundational bundle predates completeness metadata. Review the imported source docs before approval.
                </div>
              ) : null}
              {completeness.missingDocKeys.length ? (
                <div className="mt-2">
                  Missing: {completeness.missingDocKeys.join(", ")}
                </div>
              ) : null}
            </div>
          </Callout>
        ) : null}

        <div className="mt-4 flex items-center gap-3">
          <Button
            size="sm"
            onClick={() => void approveFoundational.mutateAsync({ allowIncomplete })}
            disabled={approveFoundational.isPending}
          >
            {approveFoundational.isPending ? "Approving..." : "Approve foundational"}
          </Button>
          <label className="flex items-center gap-2 text-xs text-content-muted">
            <input
              type="checkbox"
              checked={allowIncomplete}
              onChange={(e) => setAllowIncomplete(e.target.checked)}
            />
            Allow incomplete
          </label>
        </div>
      </div>
    </div>
  );
}
