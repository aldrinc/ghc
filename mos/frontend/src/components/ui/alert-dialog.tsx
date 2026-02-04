import { AlertDialog as BaseAlertDialog } from "@base-ui/react/alert-dialog";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";
import { floatingBackdrop, floatingPanel } from "@/components/ui/floating";

export const AlertDialog = BaseAlertDialog.Root;
export const AlertDialogTrigger = BaseAlertDialog.Trigger;

export const AlertDialogContent = forwardRef<HTMLDivElement, BaseAlertDialog.Popup.Props>(
  function AlertDialogContent({ className, ...props }, ref) {
    return (
      <BaseAlertDialog.Portal>
        <BaseAlertDialog.Backdrop className={floatingBackdrop()} />
        <BaseAlertDialog.Viewport className="fixed inset-0 z-dialog grid place-items-center px-4 py-6">
          <BaseAlertDialog.Popup
            ref={ref}
            className={cn(floatingPanel("w-full max-w-md p-6"), className)}
            {...props}
          />
        </BaseAlertDialog.Viewport>
      </BaseAlertDialog.Portal>
    );
  }
);

export const AlertDialogTitle = ({ className, ...props }: BaseAlertDialog.Title.Props) => (
  <BaseAlertDialog.Title {...props} className={cn("text-lg font-semibold text-content", className)} />
);

export const AlertDialogDescription = ({ className, ...props }: BaseAlertDialog.Description.Props) => (
  <BaseAlertDialog.Description {...props} className={cn("text-sm text-content-muted", className)} />
);

export const AlertDialogAction = ({ className, ...props }: BaseAlertDialog.Close.Props) => (
  <BaseAlertDialog.Close
    {...props}
    className={cn(
      "inline-flex items-center justify-center rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-contrast shadow-sm hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
      className
    )}
  />
);

export const AlertDialogCancel = ({ className, ...props }: BaseAlertDialog.Close.Props) => (
  <BaseAlertDialog.Close
    {...props}
    className={cn(
      "inline-flex items-center justify-center rounded-md border border-border bg-surface px-4 py-2 text-sm font-semibold text-content shadow-sm hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
      className
    )}
  />
);
