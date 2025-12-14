import { forwardRef } from "react";
import { Progress as BaseProgress } from "@base-ui/react/progress";
import { cn } from "@/lib/utils";

type ProgressProps = BaseProgress.Root.Props;

export const Progress = forwardRef<HTMLDivElement, ProgressProps>(function Progress({ className, ...props }, ref) {
  return (
    <BaseProgress.Root
      ref={ref}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-border", className)}
      {...props}
    >
      <BaseProgress.Indicator className="h-full bg-accent transition-all" />
    </BaseProgress.Root>
  );
});
