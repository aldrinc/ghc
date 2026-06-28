import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export type SelectOption = { label: string; value: string; disabled?: boolean; group?: string };

type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  options: SelectOption[];
  onValueChange?: (value: string) => void;
};

const SELECT_CHEVRON_BACKGROUND =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='%230B0D12' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>\")";

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, options, value, onValueChange, onChange, style, ...props },
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
        "h-[54px] w-full appearance-none rounded-[12px] border-[1.5px] border-input-border bg-input py-0 pl-[18px] pr-12 text-base font-medium tracking-normal text-content shadow-none transition-[border-color,box-shadow,background,color] duration-[var(--dur-fast)] ease-[var(--ease-out)]",
        "hover:border-input-border-focus focus-visible:border-input-border-focus focus-visible:outline-none focus-visible:ring-0 focus-visible:shadow-[0_0_0_4px_var(--input-ring)]",
        "disabled:cursor-not-allowed disabled:border-border disabled:bg-disabled disabled:text-disabled-foreground disabled:opacity-100",
        className
      )}
      style={{
        backgroundImage: SELECT_CHEVRON_BACKGROUND,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 16px center",
        ...style,
      }}
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
