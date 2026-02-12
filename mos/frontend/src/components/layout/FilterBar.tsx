import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export type FilterBarProps = HTMLAttributes<HTMLDivElement>;

export function FilterBar({ className, ...props }: FilterBarProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-2xl border border-border bg-surface p-3 shadow-sm",
        className
      )}
      {...props}
    />
  );
}

