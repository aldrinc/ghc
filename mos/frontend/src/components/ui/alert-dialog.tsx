import { AlertDialog as BaseAlertDialog } from "@base-ui/react/alert-dialog";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";
import { floatingBackdrop, floatingPanel } from "@/components/ui/floating";
import { buttonClasses } from "@/components/ui/button";

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
            className={cn(floatingPanel("w-full max-w-md p-7"), className)}
            {...props}
          />
        </BaseAlertDialog.Viewport>
      </BaseAlertDialog.Portal>
    );
  }
);

export const AlertDialogTitle = ({ className, ...props }: BaseAlertDialog.Title.Props) => (
  <BaseAlertDialog.Title {...props} className={cn("font-display text-2xl font-semibold tracking-tighter text-content", className)} />
);

export const AlertDialogDescription = ({ className, ...props }: BaseAlertDialog.Description.Props) => (
  <BaseAlertDialog.Description {...props} className={cn("mt-2 text-sm leading-normal text-content-muted", className)} />
);

export const AlertDialogAction = ({ className, ...props }: BaseAlertDialog.Close.Props) => (
  <BaseAlertDialog.Close
    {...props}
    className={buttonClasses({ className })}
  />
);

export const AlertDialogCancel = ({ className, ...props }: BaseAlertDialog.Close.Props) => (
  <BaseAlertDialog.Close
    {...props}
    className={buttonClasses({ variant: "secondary", className })}
  />
);
