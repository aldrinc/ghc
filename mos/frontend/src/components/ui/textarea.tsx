import * as React from "react";

import { cn } from "@/lib/utils";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<"textarea">>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          [
            "flex min-h-[124px] w-full resize-y rounded-[12px] border-[1.5px] border-input-border bg-input px-[18px] py-3.5 text-base font-medium leading-relaxed tracking-normal text-content shadow-none transition-[border-color,box-shadow,background,color] duration-[var(--dur-fast)] ease-[var(--ease-out)]",
            "placeholder:font-normal placeholder:text-content-muted placeholder:opacity-100 hover:border-input-border-focus",
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
Textarea.displayName = "Textarea";

export { Textarea };
