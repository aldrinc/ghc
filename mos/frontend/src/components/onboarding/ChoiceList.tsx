import type { ReactNode } from "react";
import { AlertCircle, Check, Circle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type ChoiceListItem = {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  selected?: boolean;
  disabled?: boolean;
  blocked?: boolean;
  disabledReason?: ReactNode;
  meta?: ReactNode;
};

export type ChoiceListProps = {
  items: ChoiceListItem[];
  onSelect?: (id: string) => void;
  selectionMode?: "single" | "multiple";
  variant?: "stack" | "compact" | "card";
  layout?: "stack" | "grid";
  iconStyle?: "default" | "color";
  className?: string;
  itemClassName?: string;
  "aria-label"?: string;
};

export function ChoiceList({
  items,
  onSelect,
  selectionMode = "single",
  variant = "stack",
  layout,
  iconStyle = "default",
  className,
  itemClassName,
  "aria-label": ariaLabel = "Choices",
}: ChoiceListProps) {
  const isMulti = selectionMode === "multiple";
  const resolvedLayout = layout || (variant === "card" ? "grid" : "stack");

  return (
    <div
      className={cn(resolvedLayout === "grid" ? "mos-choice-grid" : "mos-choice-stack", className)}
      role="listbox"
      aria-label={ariaLabel}
      aria-multiselectable={isMulti || undefined}
    >
      {items.map((item) => {
        const isDisabled = item.disabled || item.blocked;
        return (
          <button
            key={item.id}
            type="button"
            role="option"
            aria-selected={Boolean(item.selected)}
            aria-disabled={isDisabled || undefined}
            disabled={isDisabled}
            onClick={() => onSelect?.(item.id)}
            className={cn(
              "mos-choice",
              isMulti && "mos-choice--multi",
              variant === "compact" && "mos-choice--compact",
              variant === "card" && "mos-choice--card",
              item.selected && "is-selected",
              isDisabled && "cursor-not-allowed opacity-60",
              itemClassName,
            )}
          >
            <span
              className={cn("mos-choice-icon", iconStyle === "color" && "mos-choice-icon--color", variant === "compact" && "hidden")}
              aria-hidden={variant === "compact" || undefined}
            >
              {item.blocked ? (
                <AlertCircle className="h-4 w-4 text-danger" />
              ) : item.icon ? (
                item.icon
              ) : (
                <Circle className="h-4 w-4" />
              )}
            </span>
            <span className="mos-choice-body">
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="mos-choice-title">{item.title}</span>
                {item.blocked ? <Badge tone="danger">Blocked</Badge> : null}
                {item.meta}
              </span>
              {item.description ? <span className="mos-choice-subtitle">{item.description}</span> : null}
              {item.disabledReason ? <span className="mt-1 block text-xs text-content-muted">{item.disabledReason}</span> : null}
            </span>
            <span className="mos-choice-ring" aria-hidden="true">
              <Check className="h-3 w-3" />
            </span>
          </button>
        );
      })}
    </div>
  );
}
