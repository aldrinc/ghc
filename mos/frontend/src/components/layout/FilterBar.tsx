import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export type FilterBarProps = HTMLAttributes<HTMLDivElement>;

export function FilterBar({ className, ...props }: FilterBarProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-[12px] border-[1.5px] border-border bg-surface-2 px-4 py-3",
        className
      )}
      {...props}
    />
  );
}
