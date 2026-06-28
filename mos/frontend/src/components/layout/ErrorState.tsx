import type { HTMLAttributes, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ErrorStateProps = Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  title?: ReactNode;
  message?: ReactNode;
  onRetry?: () => void;
};

export function ErrorState({ title, message, onRetry, className, ...props }: ErrorStateProps) {
  return (
    <div
      className={cn(
        "rounded-card border border-danger/25 bg-danger-bg px-5 py-6 text-center text-sm",
        className,
      )}
      {...props}
    >
      <div className="font-semibold text-danger">{title || "Something went wrong"}</div>
      {message ? <div className="mt-1 text-content-muted">{message}</div> : null}
      {onRetry ? (
        <Button className="mt-3" variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
