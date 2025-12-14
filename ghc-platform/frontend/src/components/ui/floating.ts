import { cn } from "@/lib/utils";

export function floatingPanel(className?: string) {
  return cn(
    "rounded-lg border border-border bg-surface text-sm text-content shadow-[0_20px_60px_rgba(15,23,42,0.18)] outline-none transition duration-150",
    "data-[starting-style]:translate-y-1 data-[starting-style]:opacity-0 data-[ending-style]:translate-y-0 data-[ending-style]:opacity-100",
    className
  );
}

export function floatingBackdrop(className?: string) {
  return cn(
    "fixed inset-0 z-dialog bg-black/70 transition-opacity duration-200",
    "data-[starting-style]:opacity-0 data-[ending-style]:opacity-100",
    className
  );
}
