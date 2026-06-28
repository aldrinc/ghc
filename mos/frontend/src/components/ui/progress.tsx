import { forwardRef } from "react";
import { Progress as BaseProgress } from "@base-ui/react/progress";
import { cn } from "@/lib/utils";

type ProgressProps = BaseProgress.Root.Props;

export const Progress = forwardRef<HTMLDivElement, ProgressProps>(function Progress({ className, ...props }, ref) {
  return (
    <BaseProgress.Root
      ref={ref}
      className={cn("relative h-2 w-full overflow-hidden rounded-pill bg-border", className)}
      {...props}
    >
      <BaseProgress.Indicator className="h-full rounded-pill bg-accent transition-all duration-[var(--dur-base)] ease-[var(--ease-out)]" />
    </BaseProgress.Root>
  );
});
