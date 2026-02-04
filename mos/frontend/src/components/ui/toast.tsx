import type { ReactNode } from "react";
import { useEffect } from "react";
import * as ToastPrimitive from "@base-ui/react/toast";
import type { ToastManagerPromiseOptions } from "@base-ui/react/toast";
import { floatingPanel } from "@/components/ui/floating";
import { cn } from "@/lib/utils";

const { Toast } = ToastPrimitive;
const toastManager = Toast.createToastManager();

export type ToastOptions = {
  title: string;
  description?: string;
  type?: "success" | "error" | "info";
  timeout?: number;
};

export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider toastManager={toastManager} limit={4} timeout={5000}>
      {children}
      <ToastViewportRegion />
    </Toast.Provider>
  );
}

function ToastViewportRegion() {
  const { toasts, close } = Toast.useToastManager();

  // Auto-close limited toasts to keep list clean.
  useEffect(() => {
    toasts.forEach((toast) => {
      if (toast.limited) {
        close(toast.id);
      }
    });
  }, [toasts, close]);

  return (
    <Toast.Viewport className="pointer-events-none fixed bottom-4 right-4 z-toast flex w-96 flex-col gap-2">
      {toasts.map((toast) => (
        <Toast.Root
          key={toast.id}
          toast={toast}
          className={cn(
            floatingPanel("pointer-events-auto w-full overflow-hidden ring-1 ring-black/5"),
            toast.type === "success" && "border-l-4 border-l-success/70",
            toast.type === "error" && "border-l-4 border-l-danger/70",
            toast.type === "info" && "border-l-4 border-l-accent/70"
          )}
        >
          <Toast.Content className="p-3">
            <div className="flex items-start gap-3">
              <div className="flex-1">
                {toast.title ? (
                  <Toast.Title className="text-sm font-semibold text-content">
                    {toast.title}
                  </Toast.Title>
                ) : null}
                {toast.description ? (
                  <Toast.Description className="text-sm text-content-muted">
                    {toast.description}
                  </Toast.Description>
                ) : null}
              </div>
              <Toast.Close
                className="text-xs font-semibold text-content-muted hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
                aria-label="Close"
              >
                ✕
              </Toast.Close>
            </div>
          </Toast.Content>
        </Toast.Root>
      ))}
    </Toast.Viewport>
  );
}

export const toast = {
  success(options: string | ToastOptions) {
    const opts = typeof options === "string" ? { title: options } : options;
    return toastManager.add({ ...opts, type: "success" });
  },
  error(options: string | ToastOptions) {
    const opts = typeof options === "string" ? { title: options } : options;
    return toastManager.add({ ...opts, type: "error" });
  },
  info(options: string | ToastOptions) {
    const opts = typeof options === "string" ? { title: options } : options;
    return toastManager.add({ ...opts, type: "info" });
  },
  promise<Value>(promise: Promise<Value>, messages: ToastManagerPromiseOptions<Value, object>) {
    return toastManager.promise(promise, messages);
  },
  raw: toastManager,
};
