import { cn } from "@/lib/utils";

export function floatingPanel(className?: string) {
  return cn(
    "rounded-lg border-[1.5px] border-border bg-surface text-sm text-content shadow-xl outline-none transition duration-[var(--dur-base)] ease-[var(--ease-out)]",
    "data-[starting-style]:translate-y-1 data-[starting-style]:opacity-0 data-[ending-style]:translate-y-0 data-[ending-style]:opacity-100",
    className
  );
}

export function floatingBackdrop(className?: string) {
  return cn(
    "fixed inset-0 z-dialog bg-overlay transition-opacity duration-[var(--dur-base)] ease-[var(--ease-out)]",
    "data-[starting-style]:opacity-0 data-[ending-style]:opacity-100",
    className
  );
}
