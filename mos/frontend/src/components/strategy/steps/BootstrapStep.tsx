import { useState } from "react";

import type { useBootstrapStrategySkills } from "@/api/productStrategySkills";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type BootstrapStepProps = {
  isActive: boolean;
  isCompleted: boolean;
  bootstrap: ReturnType<typeof useBootstrapStrategySkills>;
};

export function BootstrapStep({ isActive, isCompleted, bootstrap }: BootstrapStepProps) {
  const [releaseVersion, setReleaseVersion] = useState("");
  const [strategyRoot, setStrategyRoot] = useState("");
  const [foundationalRoot, setFoundationalRoot] = useState("");

  if (isCompleted) {
    return (
      <details className="ds-card ds-card--sm shadow-none">
        <summary className="flex cursor-pointer items-center gap-2 px-4 py-3">
          <span className="text-sm font-semibold text-content">Bootstrap</span>
          <span className="text-xs text-success">Completed</span>
        </summary>
        <div className="border-t border-border px-4 py-3 text-sm text-content-muted">
          Skills release bound and foundational docs imported.
        </div>
      </details>
    );
  }

  if (!isActive) {
    return (
      <div className="ds-card ds-card--sm opacity-50 shadow-none">
        <div className="px-4 py-3">
          <div className="text-sm font-semibold text-content-muted">Bootstrap</div>
          <div className="mt-1 text-xs text-content-muted">
            Bind a skills release and import foundational source docs.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ds-card ds-card--sm ring-1 ring-accent/20 shadow-none" id="step-bootstrap">
      <div className="px-4 py-3">
        <div className="text-sm font-semibold text-content">Bootstrap skills runtime</div>
        <div className="mt-1 text-xs text-content-muted">
          Bind a skills release to this product and import the foundational source docs before running any strategy stages.
        </div>
      </div>
      <div className="border-t border-border px-4 py-4">
        <div className="grid gap-3 md:grid-cols-3">
          <Input
            value={releaseVersion}
            onChange={(e) => setReleaseVersion(e.target.value)}
            placeholder="Release version"
          />
          <Input
            value={strategyRoot}
            onChange={(e) => setStrategyRoot(e.target.value)}
            placeholder="Strategy repo root"
          />
          <Input
            value={foundationalRoot}
            onChange={(e) => setFoundationalRoot(e.target.value)}
            placeholder="Foundational docs root"
          />
        </div>
        <div className="mt-3">
          <Button
            size="sm"
            onClick={() =>
              void bootstrap.mutateAsync({
                releaseVersion: releaseVersion.trim(),
                strategyRoot: strategyRoot.trim(),
                foundationalRoot: foundationalRoot.trim(),
              })
            }
            disabled={
              bootstrap.isPending ||
              !releaseVersion.trim() ||
              !strategyRoot.trim() ||
              !foundationalRoot.trim()
            }
          >
            {bootstrap.isPending ? "Bootstrapping..." : "Bootstrap"}
          </Button>
        </div>
      </div>
    </div>
  );
}
