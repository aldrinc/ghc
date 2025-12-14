import { forwardRef } from "react";
import { Button as BaseButton, type ButtonProps as BaseButtonProps } from "@base-ui/react/button";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export type ButtonProps = BaseButtonProps & {
  variant?: Variant;
  size?: Size;
};

export function buttonClasses({
  variant = "primary",
  size = "md",
  className,
}: {
  variant?: Variant;
  size?: Size;
  className?: string;
}) {
  const variantStyles: Record<Variant, string> = {
    primary: "bg-accent text-accent-contrast border border-accent shadow-sm hover:bg-accent/90 active:bg-accent/85",
    secondary: "bg-white text-content border border-border shadow-sm hover:bg-surface-2 active:bg-surface-2",
    ghost: "text-content border border-border bg-white/80 hover:bg-surface-2 active:bg-surface-2",
    danger: "bg-danger text-white border border-danger hover:bg-danger/90 active:bg-danger/85 shadow-sm",
  };

  const sizeStyles: Record<Size, string> = {
    sm: "h-8 px-3 text-sm",
    md: "h-10 px-4 text-sm",
  };

  return cn(
    "inline-flex items-center justify-center gap-2 rounded-md font-semibold shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-60 active:translate-y-[1px]",
    variantStyles[variant],
    sizeStyles[size],
    className
  );
}

export const Button = forwardRef<HTMLElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", ...props },
  ref
) {
  return (
    <BaseButton
      ref={ref}
      className={buttonClasses({ variant, size, className })}
      {...props}
    />
  );
});
