import * as AlertDialogPrimitive from "@base-ui/react/alert-dialog";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";
import { floatingBackdrop, floatingPanel } from "@/components/ui/floating";

export const AlertDialog = AlertDialogPrimitive.Root;
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger;

export const AlertDialogContent = forwardRef<HTMLDivElement, AlertDialogPrimitive.Content.Props>(
  function AlertDialogContent({ className, ...props }, ref) {
    return (
      <AlertDialogPrimitive.Portal>
        <AlertDialogPrimitive.Backdrop className={floatingBackdrop()} />
        <AlertDialogPrimitive.Positioner className="fixed inset-0 z-dialog grid place-items-center px-4 py-6">
          <AlertDialogPrimitive.Content
            ref={ref}
            className={cn(floatingPanel("w-full max-w-md p-6"), className)}
            {...props}
          />
        </AlertDialogPrimitive.Positioner>
      </AlertDialogPrimitive.Portal>
    );
  }
);

export const AlertDialogTitle = ({ className, ...props }: AlertDialogPrimitive.Title.Props) => (
  <AlertDialogPrimitive.Title {...props} className={cn("text-lg font-semibold text-content", className)} />
);

export const AlertDialogDescription = ({ className, ...props }: AlertDialogPrimitive.Description.Props) => (
  <AlertDialogPrimitive.Description {...props} className={cn("text-sm text-content-muted", className)} />
);

export const AlertDialogAction = ({ className, ...props }: AlertDialogPrimitive.Action.Props) => (
  <AlertDialogPrimitive.Action
    {...props}
    className={cn(
      "inline-flex items-center justify-center rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-contrast shadow-sm hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
      className
    )}
  />
);

export const AlertDialogCancel = ({ className, ...props }: AlertDialogPrimitive.Cancel.Props) => (
  <AlertDialogPrimitive.Cancel
    {...props}
    className={cn(
      "inline-flex items-center justify-center rounded-md border border-border bg-surface px-4 py-2 text-sm font-semibold text-content shadow-sm hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
      className
    )}
  />
);
