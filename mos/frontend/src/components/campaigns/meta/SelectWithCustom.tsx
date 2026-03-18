import { useState } from "react";
import { Select, type SelectOption } from "@/components/ui/select";
import { Input } from "@/components/ui/input";

const CUSTOM_SENTINEL = "__custom__";

interface SelectWithCustomProps {
  options: SelectOption[];
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
}

export function SelectWithCustom({ options, value, onValueChange, placeholder }: SelectWithCustomProps) {
  const isKnown = value === "" || options.some((o) => o.value === value && o.value !== CUSTOM_SENTINEL);
  const [customMode, setCustomMode] = useState(false);

  const showInput = customMode || (!isKnown && value !== "");

  if (showInput) {
    return (
      <div className="flex items-center gap-2">
        <Input
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1"
        />
        <button
          type="button"
          className="whitespace-nowrap text-xs text-accent hover:underline"
          onClick={() => {
            setCustomMode(false);
            // Reset to first non-disabled option if current value is not in list
            if (!isKnown) {
              const first = options.find((o) => !o.disabled && o.value !== CUSTOM_SENTINEL);
              if (first) onValueChange(first.value);
            }
          }}
        >
          Use preset
        </button>
      </div>
    );
  }

  const selectOptions: SelectOption[] = [
    ...(placeholder ? [{ label: placeholder, value: "", disabled: true }] : []),
    ...options,
    { label: "Custom\u2026", value: CUSTOM_SENTINEL },
  ];

  return (
    <Select
      options={selectOptions}
      value={value}
      onValueChange={(v) => {
        if (v === CUSTOM_SENTINEL) {
          setCustomMode(true);
          onValueChange("");
        } else {
          onValueChange(v);
        }
      }}
    />
  );
}
