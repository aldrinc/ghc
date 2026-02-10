import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium",
    "transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "disabled:pointer-events-none disabled:opacity-60",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        // Primary actions in the app. `default` is kept as an alias for legacy call sites.
        primary: "bg-primary text-primary-foreground hover:bg-accent-hover active:bg-accent-active",
        default: "bg-primary text-primary-foreground hover:bg-accent-hover active:bg-accent-active",
        secondary: "border border-border bg-secondary text-secondary-foreground hover:bg-hover active:bg-active",
        outline: "border border-border bg-surface text-content hover:bg-hover active:bg-active",
        ghost: "bg-transparent text-content hover:bg-hover active:bg-active",
        link: "bg-transparent text-content underline-offset-4 hover:underline",
        destructive: "bg-danger text-white hover:opacity-90 active:opacity-80",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3",
        xs: "h-8 px-2.5 text-xs",
        lg: "h-11 px-8",
        icon: "h-10 w-10 p-0",
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
