import { Dialog } from "@base-ui/react/dialog";
import { Loader2 } from "lucide-react";

import { DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export type PublishProgressDialogProps = {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  title?: string;
  status: string;
  className?: string;
};

export function PublishProgressDialog({
  open,
  onOpenChange,
  title = "Publishing",
  status,
  className,
}: PublishProgressDialogProps) {
  return (
    <DialogRoot open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop
          className={cn(
            "fixed inset-0 z-dialog backdrop-blur-sm transition-opacity duration-200",
            "data-[starting-style]:opacity-0 data-[ending-style]:opacity-100",
          )}
          style={{ backgroundColor: "var(--first-run-backdrop)" }}
        />
        <Dialog.Viewport className="fixed inset-0 z-dialog grid place-items-center px-4 py-6">
          <Dialog.Popup
            className={cn(
              "w-full max-w-sm rounded-lg border border-border bg-surface p-5 text-content outline-none transition duration-150",
              "data-[starting-style]:translate-y-1 data-[starting-style]:opacity-0 data-[ending-style]:translate-y-0 data-[ending-style]:opacity-100",
              className,
            )}
            style={{ boxShadow: "var(--first-run-shadow-modal)" }}
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2">
                <Loader2 className="h-4 w-4 animate-spin text-accent" aria-hidden />
              </span>
              <div className="min-w-0 space-y-1">
                <DialogTitle className="text-base">{title}</DialogTitle>
                <DialogDescription className="!mt-0 leading-5">{status}</DialogDescription>
              </div>
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </DialogRoot>
  );
}
