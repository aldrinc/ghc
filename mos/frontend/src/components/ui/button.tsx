import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "relative isolate inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-pill border font-semibold tracking-normal",
    "transition-[background,border-color,color,box-shadow,transform] duration-[var(--dur-fast)] ease-[var(--ease-out)]",
    "hover:scale-[1.015] hover:shadow-[0_0_0_4px_var(--btn-halo)] active:scale-[0.98] active:shadow-[0_0_0_2px_var(--btn-halo)]",
    "focus-visible:outline-none focus-visible:ring-0 focus-visible:shadow-[0_0_0_4px_var(--btn-ring)]",
    "disabled:pointer-events-none disabled:scale-100 disabled:opacity-50 disabled:shadow-none",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        // Primary actions in the app. `default` is kept as an alias for legacy call sites.
        primary:
          "border-primary bg-primary text-primary-foreground [--btn-halo:rgba(11,13,18,0.12)] [--btn-ring:rgba(11,13,18,0.2)]",
        default:
          "border-primary bg-primary text-primary-foreground [--btn-halo:rgba(11,13,18,0.12)] [--btn-ring:rgba(11,13,18,0.2)]",
        accent:
          "border-accent bg-accent text-accent-contrast [--btn-halo:rgba(37,99,235,0.3)] [--btn-ring:rgba(37,99,235,0.35)]",
        secondary:
          "border-border bg-transparent text-content [--btn-halo:rgba(11,13,18,0.08)] [--btn-ring:rgba(11,13,18,0.10)] hover:border-primary",
        outline:
          "border-border bg-transparent text-content [--btn-halo:rgba(11,13,18,0.08)] [--btn-ring:rgba(11,13,18,0.10)] hover:border-primary",
        ghost:
          "border-transparent bg-transparent text-content [--btn-halo:rgba(11,13,18,0.06)] [--btn-ring:rgba(11,13,18,0.10)] hover:bg-hover",
        link:
          "h-auto rounded-sm border-transparent bg-transparent px-1.5 py-0 text-content underline-offset-4 [--btn-halo:transparent] [--btn-ring:rgba(11,13,18,0.12)] hover:scale-100 hover:shadow-none hover:underline active:scale-100",
        destructive:
          "border-danger bg-danger text-white [--btn-halo:rgba(239,68,68,0.22)] [--btn-ring:rgba(239,68,68,0.3)]",
      },
      size: {
        default: "h-[46px] px-[22px] text-md",
        sm: "h-9 px-4 text-sm",
        xs: "h-8 px-3 text-xs",
        lg: "h-[54px] px-7 text-base",
        xl: "h-16 px-8 text-[17px]",
        icon: "h-[46px] w-[46px] p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

type ButtonClassOptions = VariantProps<typeof buttonVariants> & {
  className?: string;
};

const buttonClasses = (options: ButtonClassOptions = {}) => cn(buttonVariants(options));

export { Button, buttonClasses, buttonVariants };
