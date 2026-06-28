import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { useEffect } from "react";
import * as ToastPrimitive from "@base-ui/react/toast";
import type { ToastManagerPromiseOptions } from "@base-ui/react/toast";
import { AlertTriangle, Check, Info, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";

const { Toast } = ToastPrimitive;
const toastManager = Toast.createToastManager();

type ToastVariant = "success" | "error" | "info" | "warning" | "loading";

export type ToastOptions = {
  title: string;
  description?: string;
  type?: ToastVariant;
  timeout?: number;
  actionProps?: ComponentPropsWithoutRef<"button">;
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
    <Toast.Viewport className="pointer-events-none fixed bottom-5 right-5 z-toast flex w-[calc(100vw-2.5rem)] max-w-[380px] flex-col gap-3">
      {toasts.map((toast) => {
        const hasDetails = Boolean(toast.description || toast.actionProps);

        return (
          <Toast.Root
            key={toast.id}
            toast={toast}
            className={cn(
              "pointer-events-auto w-full overflow-hidden rounded-[12px] border px-4 py-4 text-surface shadow-[0_18px_45px_rgba(11,13,18,0.20)] outline-none",
              "transition duration-[var(--dur-base)] ease-[var(--ease-out)] data-[limited]:hidden data-[starting-style]:translate-y-2 data-[starting-style]:opacity-0 data-[ending-style]:translate-y-0 data-[ending-style]:opacity-100",
              toast.type === "success" && "border-success/25 bg-success",
              toast.type === "error" && "border-danger/25 bg-danger",
              toast.type === "warning" && "border-warning/25 bg-warning",
              toast.type === "info" && "border-info/25 bg-info",
              (!toast.type || toast.type === "loading") && "border-surface/10 bg-content"
            )}
          >
            <Toast.Content>
              <div className={cn("flex gap-3", hasDetails ? "items-start" : "items-center")}>
                <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface/10 text-surface", hasDetails && "mt-0.5")}>
                  {toast.type === "success" ? <Check className="h-3.5 w-3.5" strokeWidth={2.5} /> : null}
                  {toast.type === "error" || toast.type === "warning" ? <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2.3} /> : null}
                  {toast.type === "info" ? <Info className="h-3.5 w-3.5" strokeWidth={2.3} /> : null}
                  {!toast.type || toast.type === "loading" ? <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.3} /> : null}
                </span>
                <div className="min-w-0 flex-1">
                  {toast.title ? (
                    <Toast.Title className="text-sm font-semibold leading-5 text-surface">
                      {toast.title}
                    </Toast.Title>
                  ) : null}
                  {toast.description ? (
                    <Toast.Description className="mt-0.5 text-sm leading-5 text-surface/80">
                      {toast.description}
                    </Toast.Description>
                  ) : null}
                  {toast.actionProps ? (
                    <Toast.Action
                      {...toast.actionProps}
                      className={cn(
                        "mt-3 inline-flex min-h-8 items-center rounded-md bg-surface/10 px-3 text-xs font-semibold text-surface transition hover:bg-surface/20 focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_rgba(255,255,255,0.24)]",
                        toast.actionProps.className
                      )}
                    />
                  ) : null}
                </div>
                <Toast.Close
                  className={cn(
                    "-mr-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-surface/62 transition hover:bg-surface/10 hover:text-surface focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_rgba(255,255,255,0.24)]",
                    hasDetails && "-mt-1"
                  )}
                  aria-label="Close"
                >
                  <X className="h-3.5 w-3.5" strokeWidth={2.2} />
                </Toast.Close>
              </div>
            </Toast.Content>
          </Toast.Root>
        );
      })}
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
  warning(options: string | ToastOptions) {
    const opts = typeof options === "string" ? { title: options } : options;
    return toastManager.add({ ...opts, type: "warning" });
  },
  loading(options: string | ToastOptions) {
    const opts = typeof options === "string" ? { title: options } : options;
    return toastManager.add({ ...opts, type: "loading", timeout: opts.timeout ?? 0 });
  },
  promise<Value>(promise: Promise<Value>, messages: ToastManagerPromiseOptions<Value, object>) {
    return toastManager.promise(promise, messages);
  },
  raw: toastManager,
};
