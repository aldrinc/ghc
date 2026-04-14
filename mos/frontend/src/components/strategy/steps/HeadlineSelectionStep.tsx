import { useMemo, useState } from "react";

import type { StrategySkillsBundleItem } from "@/api/productStrategySkills";
import type { useSelectStrategyHeadline } from "@/api/productStrategySkills";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

type SelectionSummary = {
  id: string;
  label: string;
  rationale: string;
};

type HeadlineSelectionStepProps = {
  isActive: boolean;
  isCompleted: boolean;
  isUpcoming: boolean;
  workingHeadlinePoolItem?: StrategySkillsBundleItem | null;
  activeHeadlineSelection: SelectionSummary | null;
  selectHeadline: ReturnType<typeof useSelectStrategyHeadline>;
};

function extractHeadlines(item?: StrategySkillsBundleItem | null) {
  const payload = item?.artifactData?.json;
  const headlines = Array.isArray((payload as { headlines?: unknown[] } | undefined)?.headlines)
    ? ((payload as { headlines: Array<Record<string, unknown>> }).headlines ?? [])
    : [];
  return headlines
    .map((entry) => {
      const id = String(entry.headlineId ?? "").trim();
      const label = String(entry.headline ?? "").trim();
      if (!id || !label) return null;
      return { id, label };
    })
    .filter((e): e is { id: string; label: string } => Boolean(e));
}

export function HeadlineSelectionStep({
  isActive,
  isCompleted,
  isUpcoming,
  workingHeadlinePoolItem,
  activeHeadlineSelection,
  selectHeadline,
}: HeadlineSelectionStepProps) {
  const [selectedHeadlineId, setSelectedHeadlineId] = useState("");
  const [rationale, setRationale] = useState("Approved after review.");

  const headlines = useMemo(() => extractHeadlines(workingHeadlinePoolItem), [workingHeadlinePoolItem]);

  const headlineOptions = useMemo(
    () => headlines.map((h) => ({ label: h.label, value: h.id })),
    [headlines],
  );

  if (isCompleted && activeHeadlineSelection) {
    return (
      <details className="ds-card ds-card--sm shadow-none">
        <summary className="flex cursor-pointer items-center gap-2 px-4 py-3">
          <span className="text-sm font-semibold text-content">Select Headline</span>
          <Badge tone="success">Selected</Badge>
          <span className="ml-auto truncate text-xs text-content-muted">{activeHeadlineSelection.label}</span>
        </summary>
        <div className="border-t border-border px-4 py-3 text-sm text-content-muted">
          {activeHeadlineSelection.rationale}
        </div>
      </details>
    );
  }

  if (isUpcoming || (!isActive && !headlines.length)) {
    return (
      <div className="ds-card ds-card--sm opacity-50 shadow-none">
        <div className="px-4 py-3">
          <div className="text-sm font-semibold text-content-muted">Select Headline</div>
          <div className="mt-1 text-xs text-content-muted">
            Pick a headline from the headline pool after running stage 6.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ds-card ds-card--sm ring-1 ring-accent/20 shadow-none" id="step-headline">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-semibold text-content">Select Headline</div>
          <Badge tone={activeHeadlineSelection ? "success" : "warning"}>
            {activeHeadlineSelection ? "Selected" : "Selection required"}
          </Badge>
        </div>
        <div className="mt-1 text-xs text-content-muted">
          Choose the winning headline from {headlines.length} candidates.
        </div>
      </div>

      {headlines.length ? (
        <div className="border-t border-border px-4 py-4">
          <div className="space-y-2">
            {headlines.map((h) => {
              const isSelected = h.id === activeHeadlineSelection?.id;
              return (
                <div
                  key={h.id}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border bg-surface-2 px-4 py-2"
                >
                  <span className="text-sm text-content">{h.label}</span>
                  {isSelected ? <Badge tone="success">Live</Badge> : null}
                </div>
              );
            })}
          </div>

          <div className="mt-4 border-t border-border pt-4">
            <div className="text-xs font-semibold text-content-muted">Make your selection</div>
            <div className="mt-2 grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
              <Select
                value={selectedHeadlineId}
                onValueChange={setSelectedHeadlineId}
                options={[{ label: "Choose a headline", value: "" }, ...headlineOptions]}
              />
              <Textarea value={rationale} onChange={(e) => setRationale(e.target.value)} />
            </div>
            <div className="mt-3">
              <Button
                size="sm"
                onClick={() =>
                  void selectHeadline.mutateAsync({
                    selectedId: selectedHeadlineId,
                    rationale: rationale.trim(),
                  })
                }
                disabled={selectHeadline.isPending || !selectedHeadlineId || !rationale.trim()}
              >
                {selectHeadline.isPending ? "Selecting..." : "Approve headline"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
