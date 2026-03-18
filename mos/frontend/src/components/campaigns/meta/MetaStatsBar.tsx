import { cn } from "@/lib/utils";
import { useMetaPublishContext } from "./MetaPublishProvider";

type StatPill = {
  label: string;
  value: number;
  tone: "neutral" | "success" | "warning" | "danger";
};

function pillClass(tone: StatPill["tone"]) {
  return cn(
    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold",
    tone === "success" && "border-success/30 bg-success/10 text-success",
    tone === "warning" && "border-warning/30 bg-warning/10 text-warning",
    tone === "danger" && "border-danger/30 bg-danger/10 text-danger",
    tone === "neutral" && "border-border bg-surface-2 text-content-muted",
  );
}

export function MetaStatsBar() {
  const {
    assetBriefIds,
    pipeline,
    creativeSpecCount,
    adsetSpecCount,
    includedPackageItems,
    excludedPackageCount,
  } = useMetaPublishContext();

  const stats: StatPill[] = [
    {
      label: "Briefs",
      value: assetBriefIds.length,
      tone: assetBriefIds.length > 0 ? "neutral" : "warning",
    },
    {
      label: "Assets",
      value: pipeline.length,
      tone: pipeline.length > 0 ? "success" : "neutral",
    },
    {
      label: "Specs",
      value: creativeSpecCount,
      tone: creativeSpecCount > 0 ? "success" : pipeline.length > 0 ? "warning" : "neutral",
    },
    {
      label: "Ad sets",
      value: adsetSpecCount,
      tone: adsetSpecCount > 0 ? "neutral" : "neutral",
    },
    {
      label: "Included",
      value: includedPackageItems.length,
      tone: includedPackageItems.length > 0 ? "success" : pipeline.length > 0 ? "warning" : "neutral",
    },
    {
      label: "Excluded",
      value: excludedPackageCount,
      tone: excludedPackageCount > 0 ? "danger" : "neutral",
    },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2">
      {stats.map((stat) => (
        <span key={stat.label} className={pillClass(stat.tone)}>
          <span className="font-bold">{stat.value}</span>
          <span className="text-[10px] uppercase tracking-wider">{stat.label}</span>
        </span>
      ))}
    </div>
  );
}
