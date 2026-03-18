import { Select } from "@/components/ui/select";
import { Callout } from "@/components/ui/callout";
import { useMetaPublishContext, readString } from "./MetaPublishProvider";

export function MetaFunnelScopeBar() {
  const {
    requiresFunnelScope,
    activeFunnelId,
    funnelScopeOptions,
    setSelectedFunnelId,
    latestGenerationFunnelIds,
  } = useMetaPublishContext();

  const needsFunnelSelection = requiresFunnelScope && latestGenerationFunnelIds.length > 1 && !activeFunnelId;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span className="shrink-0 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">
          {requiresFunnelScope ? "Funnel scope" : "Delivery scope"}
        </span>
        {requiresFunnelScope ? (
          <Select
            value={activeFunnelId || ""}
            onValueChange={(value) => setSelectedFunnelId(readString(value))}
            options={
              funnelScopeOptions.length
                ? [{ label: "Select funnel", value: "" }, ...funnelScopeOptions]
                : [{ label: "No funnels in latest generation", value: "" }]
            }
            disabled={funnelScopeOptions.length <= 1}
          />
        ) : (
          <span className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-content">
            External destination URLs
          </span>
        )}
      </div>

      {needsFunnelSelection ? (
        <Callout variant="warning" size="sm">
          Select a funnel to continue. Meta review, QA, and publish all operate on one funnel at a time.
        </Callout>
      ) : null}
    </div>
  );
}
