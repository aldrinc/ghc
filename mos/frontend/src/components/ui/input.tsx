import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          [
            "flex h-[54px] w-full rounded-[12px] border-[1.5px] border-input-border bg-input px-[18px] text-base font-medium tracking-normal text-content shadow-none transition-[border-color,box-shadow,background,color] duration-[var(--dur-fast)] ease-[var(--ease-out)]",
            "placeholder:font-normal placeholder:text-content-muted placeholder:opacity-100 hover:border-input-border-focus",
            "file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-content",
            "focus-visible:border-input-border-focus focus-visible:outline-none focus-visible:ring-0 focus-visible:shadow-[0_0_0_4px_var(--input-ring)]",
            "disabled:cursor-not-allowed disabled:border-border disabled:bg-disabled disabled:text-disabled-foreground disabled:opacity-100",
          ].join(" "),
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
