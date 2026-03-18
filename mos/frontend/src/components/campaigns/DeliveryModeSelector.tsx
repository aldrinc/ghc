import { cn } from "@/lib/utils";
import type { DeliveryMode } from "@/types/delivery";

const modes: Array<{
  value: DeliveryMode;
  label: string;
  description: string;
}> = [
  {
    value: "internal_funnel",
    label: "Internal funnel",
    description: "MOS-hosted landing pages managed in the funnels workspace.",
  },
  {
    value: "external_urls",
    label: "External URLs",
    description: "Your own landing pages hosted outside MOS.",
  },
];

/**
 * Radio-card selector for choosing the campaign delivery mode.
 */
export function DeliveryModeSelector({
  value,
  onChange,
  disabled,
}: {
  value: DeliveryMode;
  onChange: (mode: DeliveryMode) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {modes.map((mode) => {
        const selected = value === mode.value;
        return (
          <button
            key={mode.value}
            type="button"
            disabled={disabled}
            onClick={() => onChange(mode.value)}
            className={cn(
              "rounded-lg border px-4 py-3 text-left transition",
              selected
                ? "border-accent bg-accent/5 ring-2 ring-accent/20"
                : "border-border bg-surface hover:border-accent/50",
              disabled && "cursor-not-allowed opacity-50",
            )}
          >
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "h-4 w-4 rounded-full border-2",
                  selected ? "border-accent bg-accent" : "border-border bg-surface",
                )}
              />
              <div className="text-sm font-semibold text-content">{mode.label}</div>
            </div>
            <div className="mt-1 pl-6 text-xs text-content-muted">{mode.description}</div>
          </button>
        );
      })}
    </div>
  );
}
