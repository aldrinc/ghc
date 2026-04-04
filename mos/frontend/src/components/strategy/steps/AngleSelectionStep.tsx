import { useMemo, useState } from "react";

import type {
  StrategySkillsBundle,
  StrategySkillsBundleItem,
} from "@/api/productStrategySkills";
import type { useSelectStrategyAngle } from "@/api/productStrategySkills";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

type AngleEntry = {
  id: string;
  label: string;
  description: string;
  mechanism: string;
  evidence: string[];
};

type SelectionSummary = {
  id: string;
  label: string;
  rationale: string;
};

type AngleSelectionStepProps = {
  isActive: boolean;
  isCompleted: boolean;
  isUpcoming: boolean;
  productTitle: string;
  workingAngleLibraryItem?: StrategySkillsBundleItem | null;
  approvedAngleLibraryItem?: StrategySkillsBundleItem | null;
  activeAngleSelection: SelectionSummary | null;
  selectAngle: ReturnType<typeof useSelectStrategyAngle>;
};

function extractAngles(item?: StrategySkillsBundleItem | null): AngleEntry[] {
  const payload = item?.artifactData?.json;
  const angles = Array.isArray((payload as { angles?: unknown[] } | undefined)?.angles)
    ? ((payload as { angles: Array<Record<string, unknown>> }).angles ?? [])
    : [];
  return angles
    .map((entry) => {
      const id = String(entry.angleId ?? "").trim();
      const label = String(entry.angleName ?? "").trim();
      if (!id || !label) return null;
      return {
        id,
        label,
        description: String(entry.description ?? "").trim(),
        mechanism: String(entry.mechanism ?? "").trim(),
        evidence: Array.isArray(entry.evidence)
          ? entry.evidence.map((v) => String(v ?? "").trim()).filter(Boolean)
          : [],
      };
    })
    .filter((e): e is AngleEntry => Boolean(e));
}

export function AngleSelectionStep({
  isActive,
  isCompleted,
  isUpcoming,
  productTitle,
  workingAngleLibraryItem,
  approvedAngleLibraryItem,
  activeAngleSelection,
  selectAngle,
}: AngleSelectionStepProps) {
  const [selectedAngleId, setSelectedAngleId] = useState("");
  const [rationale, setRationale] = useState("Approved after review.");

  const angles = useMemo(
    () => extractAngles(workingAngleLibraryItem ?? approvedAngleLibraryItem),
    [workingAngleLibraryItem, approvedAngleLibraryItem],
  );

  const angleOptions = useMemo(
    () => angles.map((a) => ({ label: a.label, value: a.id })),
    [angles],
  );

  if (isCompleted && activeAngleSelection) {
    return (
      <details className="ds-card ds-card--sm shadow-none">
        <summary className="flex cursor-pointer items-center gap-2 px-4 py-3">
          <span className="text-sm font-semibold text-content">Select Angle</span>
          <Badge tone="success">Selected</Badge>
          <span className="ml-auto text-xs text-content-muted">{activeAngleSelection.label}</span>
        </summary>
        <div className="border-t border-border px-4 py-3 text-sm text-content-muted">
          {activeAngleSelection.rationale}
        </div>
      </details>
    );
  }

  if (isUpcoming || (!isActive && !angles.length)) {
    return (
      <div className="ds-card ds-card--sm opacity-50 shadow-none">
        <div className="px-4 py-3">
          <div className="text-sm font-semibold text-content-muted">Select Angle</div>
          <div className="mt-1 text-xs text-content-muted">
            Pick an angle from the angle library after running stage 2.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ds-card ds-card--sm ring-1 ring-accent/20 shadow-none" id="step-angle">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-semibold text-content">Select Angle</div>
          <Badge tone={activeAngleSelection ? "success" : "warning"}>
            {activeAngleSelection ? "Selected" : "Selection required"}
          </Badge>
        </div>
        <div className="mt-1 text-xs text-content-muted">
          Choose the winning angle for {productTitle} from {angles.length} candidates.
        </div>
      </div>

      {angles.length ? (
        <div className="border-t border-border px-4 py-4">
          <div className="grid gap-3 xl:grid-cols-2">
            {angles.map((entry) => {
              const isSelected = entry.id === activeAngleSelection?.id;
              return (
                <div key={entry.id} className="rounded-lg border border-border bg-surface-2 px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-sm font-semibold text-content">{entry.label}</div>
                    {isSelected ? <Badge tone="success">Live</Badge> : null}
                  </div>
                  {entry.description ? (
                    <div className="mt-2 text-xs text-content-muted">{entry.description}</div>
                  ) : null}
                  {entry.mechanism ? (
                    <div className="mt-2 text-xs text-content-muted">
                      <span className="font-semibold">Mechanism:</span> {entry.mechanism}
                    </div>
                  ) : null}
                  {entry.evidence.length ? (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs font-medium text-content-muted">
                        Evidence ({entry.evidence.length})
                      </summary>
                      <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-content-muted">
                        {entry.evidence.map((e) => (
                          <li key={`${entry.id}-${e}`}>{e}</li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="mt-4 border-t border-border pt-4">
            <div className="text-xs font-semibold text-content-muted">Make your selection</div>
            <div className="mt-2 grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
              <Select
                value={selectedAngleId}
                onValueChange={setSelectedAngleId}
                options={[{ label: "Choose an angle", value: "" }, ...angleOptions]}
              />
              <Textarea value={rationale} onChange={(e) => setRationale(e.target.value)} />
            </div>
            <div className="mt-3">
              <Button
                size="sm"
                onClick={() =>
                  void selectAngle.mutateAsync({
                    selectedId: selectedAngleId,
                    rationale: rationale.trim(),
                  })
                }
                disabled={selectAngle.isPending || !selectedAngleId || !rationale.trim()}
              >
                {selectAngle.isPending ? "Selecting..." : "Approve angle"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
