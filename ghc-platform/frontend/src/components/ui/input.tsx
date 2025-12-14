import { forwardRef } from "react";
import { Input as BaseInput, type InputProps as BaseInputProps } from "@base-ui/react/input";
import { cn } from "@/lib/utils";

export type InputProps = BaseInputProps;

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ className, ...props }, ref) {
  return (
    <BaseInput
      ref={ref}
      className={cn(
        "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
        "data-[invalid]:border-danger data-[invalid]:ring-danger/30 data-[invalid]:ring-2 data-[invalid]:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-60 placeholder:text-content-muted",
        className
      )}
      {...props}
    />
  );
});
