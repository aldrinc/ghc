import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export type FilterBarProps = HTMLAttributes<HTMLDivElement>;

export function FilterBar({ className, ...props }: FilterBarProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2",
        className
      )}
      {...props}
    />
  );
}

