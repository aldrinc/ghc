import { Menu as BaseMenu } from "@base-ui/react/menu";
import { forwardRef } from "react";
import { floatingPanel } from "@/components/ui/floating";
import { cn } from "@/lib/utils";

export const Menu = BaseMenu.Root;
export const MenuTrigger = BaseMenu.Trigger;

export const MenuContent = forwardRef<HTMLDivElement, BaseMenu.Content.Props>(function MenuContent(
  { className, ...props },
  ref
) {
  return (
    <BaseMenu.Portal>
      <BaseMenu.Positioner className="z-dropdown">
        <BaseMenu.Popup
          ref={ref}
          className={cn(
            floatingPanel("min-w-[10rem] p-1 opacity-100 data-[open]:opacity-100"),
            className
          )}
          {...props}
        />
      </BaseMenu.Positioner>
    </BaseMenu.Portal>
  );
});

export const MenuItem = forwardRef<HTMLDivElement, BaseMenu.Item.Props>(function MenuItem(
  { className, ...props },
  ref
) {
  return (
    <BaseMenu.Item
      ref={ref}
      className={cn(
        "flex cursor-pointer select-none items-center gap-2 rounded-[8px] px-3.5 py-[11px] text-content transition-colors",
        "text-[14.5px] font-medium tracking-normal",
        "hover:bg-hover focus:bg-hover data-[highlighted]:bg-hover",
        "focus-visible:outline-none focus-visible:ring-0 focus-visible:shadow-[0_0_0_4px_var(--ring)]",
        className
      )}
      {...props}
    />
  );
});

export const MenuSeparator = ({ className, ...props }: BaseMenu.Separator.Props) => (
  <BaseMenu.Separator {...props} className={cn("my-1 h-px bg-border", className)} />
);
