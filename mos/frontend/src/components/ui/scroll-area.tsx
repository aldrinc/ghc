import { forwardRef, type ReactNode } from "react";
import { ScrollArea as BaseScrollArea } from "@base-ui/react/scroll-area";
import { cn } from "@/lib/utils";

type ScrollAreaProps = BaseScrollArea.Root.Props & {
  viewportClassName?: string;
  children: ReactNode;
};

export const ScrollArea = forwardRef<HTMLDivElement, ScrollAreaProps>(function ScrollArea(
  { className, viewportClassName, children, ...props },
  ref
) {
  return (
    <BaseScrollArea.Root
      ref={ref}
      className={cn("relative overflow-hidden rounded-md border border-border bg-surface", className)}
      {...props}
    >
      <BaseScrollArea.Viewport className={cn("h-full w-full", viewportClassName)}>
        <BaseScrollArea.Content>{children}</BaseScrollArea.Content>
      </BaseScrollArea.Viewport>
      <BaseScrollArea.Scrollbar orientation="vertical" className="flex touch-none select-none p-0.5">
        <BaseScrollArea.Thumb className="flex-1 rounded-full bg-content-muted/30" />
      </BaseScrollArea.Scrollbar>
      <BaseScrollArea.Scrollbar orientation="horizontal" className="flex touch-none select-none p-0.5">
        <BaseScrollArea.Thumb className="flex-1 rounded-full bg-content-muted/30" />
      </BaseScrollArea.Scrollbar>
      <BaseScrollArea.Corner className="bg-border" />
    </BaseScrollArea.Root>
  );
});
