import { useCallback, useEffect, useRef, useState } from "react";
import { Bot } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetOverlay,
  SheetPortal,
} from "@/components/animate-ui/primitives/radix/sheet";
import { PageAgentSidebarContent, type PageAgentSidebarContentProps } from "./PageAgentSidebar";

type Props = Omit<PageAgentSidebarContentProps, "onClose"> & {
  /** Start the panel open. */
  defaultOpen?: boolean;
};

export function PageAgentPanel({ defaultOpen = false, enabled = true, ...rest }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Track unread assistant turns while panel is closed
  const [hasUnread, setHasUnread] = useState(false);
  const lastSeenTurnCountRef = useRef(0);

  // Keyboard shortcut: Cmd/Ctrl+Shift+H
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "h" && e.shiftKey && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const handleOpenChange = useCallback((nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen) {
      setHasUnread(false);
    }
  }, []);

  // Don't render anything when agent is not available
  if (!enabled) return null;

  return (
    <>
      {/* Floating trigger button — hidden when panel is open */}
      {!open && (
        <button
          ref={triggerRef}
          type="button"
          onClick={() => handleOpenChange(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2.5 rounded-full border border-border bg-surface px-4 py-2.5 text-sm font-medium text-content shadow-lg transition-all hover:shadow-xl hover:scale-[1.02] active:scale-[0.98]"
        >
          <div className="relative flex h-7 w-7 items-center justify-center rounded-full bg-content text-surface">
            <Bot className="h-3.5 w-3.5" />
            {hasUnread && (
              <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface bg-accent" />
            )}
          </div>
          Hermes
          <kbd className="hidden text-[10px] text-content-muted sm:inline">
            {navigator.platform?.includes("Mac") ? "\u2318" : "Ctrl"}{"\u21E7"}H
          </kbd>
        </button>
      )}

      {/* Sheet overlay panel */}
      <Sheet open={open} onOpenChange={handleOpenChange}>
        <SheetPortal>
          <SheetOverlay className="fixed inset-0 z-50 bg-black/10" />
          <SheetContent
            side="right"
            className="z-50 w-[28rem] max-w-[90vw] border-l border-border bg-surface shadow-2xl"
            style={{ height: "100vh" }}
            onOpenAutoFocus={(e) => e.preventDefault()}
          >
            <PageAgentSidebarContent
              {...rest}
              enabled={enabled}
              onClose={() => handleOpenChange(false)}
            />
          </SheetContent>
        </SheetPortal>
      </Sheet>
    </>
  );
}
