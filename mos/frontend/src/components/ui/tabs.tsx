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
        "inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-[12px] border-[1.5px] border-border bg-surface-2 p-1",
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
        "inline-flex min-w-0 flex-1 items-center justify-center rounded-[8px] px-4 py-2 text-sm font-semibold tracking-normal text-content-muted transition-[background,color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease-out)] data-[selected]:bg-surface data-[selected]:shadow-sm data-[selected]:text-content focus-visible:outline-none focus-visible:ring-0 focus-visible:shadow-[0_0_0_4px_var(--ring)] sm:min-w-[104px] sm:flex-none",
        className
      )}
      {...props}
    />
  );
});

type TabsContentProps = BaseTabs.Panel.Props & {
  /** @deprecated TabsContent is now flush by default */
  flush?: boolean;
};

export const TabsContent = forwardRef<HTMLDivElement, TabsContentProps>(function TabsContent(
  { className, flush: _flush, ...props },
  ref
) {
  return (
    <BaseTabs.Panel
      ref={ref}
      className={cn("mt-4", className)}
      {...props}
    />
  );
});
