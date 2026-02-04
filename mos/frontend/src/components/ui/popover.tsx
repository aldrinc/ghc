import * as PopoverPrimitive from "@base-ui/react/popover";
import { forwardRef } from "react";
import { floatingPanel } from "@/components/ui/floating";
import { cn } from "@/lib/utils";

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;

export const PopoverContent = forwardRef<HTMLDivElement, PopoverPrimitive.Content.Props>(function PopoverContent(
  { className, ...props },
  ref
) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner className="z-dropdown">
        <PopoverPrimitive.Popup
          ref={ref}
          className={cn(floatingPanel("min-w-[12rem] p-4 data-[open]:opacity-100 data-[closed]:opacity-100"), className)}
          {...props}
        />
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  );
});
