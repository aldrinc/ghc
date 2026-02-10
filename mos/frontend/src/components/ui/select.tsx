import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export type SelectOption = { label: string; value: string };

type SelectProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "onChange"> & {
  options: SelectOption[];
  onValueChange?: (value: string) => void;
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, options, value, onValueChange, onChange, ...props },
  ref
) {
  return (
    <select
      ref={ref}
      value={value}
      onChange={(e) => {
        onChange?.(e);
        onValueChange?.(e.target.value);
      }}
      className={cn(
        "w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content shadow-sm transition",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:border-input-border-focus",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
      {...props}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
});
