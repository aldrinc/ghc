import * as TooltipPrimitive from "@base-ui/react/tooltip";
import { forwardRef } from "react";
import { floatingPanel } from "@/components/ui/floating";
import { cn } from "@/lib/utils";

export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

export const TooltipContent = forwardRef<HTMLDivElement, TooltipPrimitive.Content.Props>(function TooltipContent(
  { className, ...props },
  ref
) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Positioner className="z-dropdown">
        <TooltipPrimitive.Popup
          ref={ref}
          className={cn(
            floatingPanel("bg-content text-surface text-xs px-3 py-2 data-[open]:opacity-100 data-[closed]:opacity-100"),
            className
          )}
          {...props}
        />
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  );
});
