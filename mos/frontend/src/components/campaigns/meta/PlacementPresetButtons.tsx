import { Button } from "@/components/ui/button";
import {
  META_PLACEMENT_PRESETS,
  formatPlacementPresetJson,
  placementPresetIsActive,
} from "@/lib/metaAdsConstants";

interface PlacementPresetButtonsProps {
  placementsJson: string;
  onPlacementsJsonChange: (value: string) => void;
}

export function PlacementPresetButtons({
  placementsJson,
  onPlacementsJsonChange,
}: PlacementPresetButtonsProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-content-muted">Quick-fill:</span>
      {META_PLACEMENT_PRESETS.map((preset) => (
        <Button
          key={preset.label}
          type="button"
          variant={placementPresetIsActive(placementsJson, preset.value) ? "primary" : "secondary"}
          size="xs"
          onClick={() => onPlacementsJsonChange(formatPlacementPresetJson(preset.value))}
        >
          {preset.label}
        </Button>
      ))}
    </div>
  );
}
