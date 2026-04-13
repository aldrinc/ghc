import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export type SelectOption = { label: string; value: string; disabled?: boolean; group?: string };

type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  options: SelectOption[];
  onValueChange?: (value: string) => void;
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, options, value, onValueChange, onChange, ...props },
  ref
) {
  const groupedOptions = options.reduce<
    Array<{ group: string | null; options: SelectOption[] }>
  >((groups, option) => {
    const group = typeof option.group === "string" && option.group.trim() ? option.group : null;
    const existing = groups.find((entry) => entry.group === group);
    if (existing) {
      existing.options.push(option);
      return groups;
    }
    groups.push({ group, options: [option] });
    return groups;
  }, []);

  return (
    <select
      ref={ref}
      value={value}
      onChange={(e) => {
        onChange?.(e);
        onValueChange?.(e.target.value);
      }}
      className={cn(
        "h-9 w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content transition",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:border-input-border-focus",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
      {...props}
    >
      {groupedOptions.map((entry) => {
        if (!entry.group) {
          return entry.options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ));
        }
        return (
          <optgroup key={entry.group} label={entry.group}>
            {entry.options.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </optgroup>
        );
      })}
    </select>
  );
});
