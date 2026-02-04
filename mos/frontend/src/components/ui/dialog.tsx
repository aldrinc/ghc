import { Dialog } from "@base-ui/react/dialog";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";
import { floatingBackdrop, floatingPanel } from "@/components/ui/floating";

export const DialogRoot = Dialog.Root;
export const DialogTrigger = Dialog.Trigger;

export const DialogContent = forwardRef<HTMLDivElement, Dialog.Popup.Props>(function DialogContent(
  { className, ...props },
  ref
) {
  return (
    <Dialog.Portal>
      <Dialog.Backdrop className={floatingBackdrop()} />
      <Dialog.Viewport className="fixed inset-0 z-dialog grid place-items-center px-4 py-6">
        <Dialog.Popup
          ref={ref}
          className={cn(floatingPanel("w-full max-w-lg p-6"), className)}
          {...props}
        />
      </Dialog.Viewport>
    </Dialog.Portal>
  );
});

export const DialogTitle = ({ className, ...props }: Dialog.Title.Props) => (
  <Dialog.Title {...props} className={cn("text-lg font-semibold text-content", className)} />
);

export const DialogDescription = ({ className, ...props }: Dialog.Description.Props) => (
  <Dialog.Description {...props} className={cn("text-sm text-content-muted", className)} />
);

export const DialogClose = Dialog.Close;
