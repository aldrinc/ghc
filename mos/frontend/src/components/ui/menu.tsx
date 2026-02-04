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
        "flex cursor-pointer select-none items-center gap-2 rounded px-2 py-1.5 text-content transition-colors",
        "hover:bg-surface-2 focus:bg-surface-2 data-[highlighted]:bg-surface-2",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
        className
      )}
      {...props}
    />
  );
});

export const MenuSeparator = ({ className, ...props }: BaseMenu.Separator.Props) => (
  <BaseMenu.Separator {...props} className={cn("my-1 h-px bg-border", className)} />
);
