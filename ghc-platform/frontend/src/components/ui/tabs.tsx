import { Tabs as BaseTabs } from "@base-ui/react/tabs";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Tabs = BaseTabs.Root;

export const TabsList = forwardRef<HTMLDivElement, BaseTabs.List.Props>(function TabsList(
  { className, ...props },
  ref
) {
  return (
    <BaseTabs.List
      ref={ref}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-border bg-surface-2 p-1 shadow-sm",
        className
      )}
      {...props}
    />
  );
});

export const TabsTrigger = forwardRef<HTMLButtonElement, BaseTabs.Tab.Props>(function TabsTrigger(
  { className, ...props },
  ref
) {
  return (
    <BaseTabs.Tab
      ref={ref}
      className={cn(
        "inline-flex min-w-[100px] items-center justify-center rounded-md px-3 py-2 text-sm font-semibold text-content-muted transition data-[selected]:bg-surface data-[selected]:shadow-sm data-[selected]:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-2",
        className
      )}
      {...props}
    />
  );
});

export const TabsContent = forwardRef<HTMLDivElement, BaseTabs.Panel.Props>(function TabsContent(
  { className, ...props },
  ref
) {
  return (
    <BaseTabs.Panel
      ref={ref}
      className={cn("mt-4 rounded-md border border-border bg-surface p-4 shadow-sm", className)}
      {...props}
    />
  );
});
