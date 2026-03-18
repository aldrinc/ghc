import { META_SPECIAL_AD_CATEGORIES } from "@/lib/metaAdsConstants";

interface SpecialAdCategoriesCheckboxGroupProps {
  value: string;
  onChange: (value: string) => void;
}

export function SpecialAdCategoriesCheckboxGroup({ value, onChange }: SpecialAdCategoriesCheckboxGroupProps) {
  const selected = new Set(
    value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
  );

  function toggle(cat: string) {
    const next = new Set(selected);
    if (next.has(cat)) {
      next.delete(cat);
    } else {
      next.add(cat);
    }
    onChange([...next].join(", "));
  }

  return (
    <div className="flex flex-wrap gap-2">
      {META_SPECIAL_AD_CATEGORIES.map((cat) => {
        const checked = selected.has(cat.value);
        return (
          <label
            key={cat.value}
            className={[
              "flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs transition",
              checked
                ? "border-accent bg-accent/10 text-accent"
                : "border-border bg-surface text-content-muted hover:border-input-border-focus",
            ].join(" ")}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={() => toggle(cat.value)}
              className="sr-only"
            />
            <span
              className={[
                "inline-flex h-3.5 w-3.5 items-center justify-center rounded-sm border text-[10px]",
                checked ? "border-accent bg-accent text-white" : "border-border bg-input",
              ].join(" ")}
            >
              {checked ? "\u2713" : ""}
            </span>
            {cat.label}
          </label>
        );
      })}
      {selected.size === 0 ? (
        <span className="py-1.5 text-xs text-content-muted">None (most campaigns)</span>
      ) : null}
    </div>
  );
}
