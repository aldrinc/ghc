import { cn } from "@/lib/utils";

export type CreativeFilterState = {
  search: string;
  specStatus: "all" | "ready" | "missing";
  violationFilter: "all" | "has_violations" | "clean";
  angleFilter: string; // "all" or angle name
};

export const DEFAULT_FILTER_STATE: CreativeFilterState = {
  search: "",
  specStatus: "all",
  violationFilter: "all",
  angleFilter: "all",
};

/**
 * Filter bar for the creative review grid.
 * Provides search, spec status, violation, and angle filters.
 */
export function CreativeFilterBar({
  filters,
  onChange,
  angles,
  totalCount,
  filteredCount,
  violationFilterEnabled = true,
}: {
  filters: CreativeFilterState;
  onChange: (next: CreativeFilterState) => void;
  angles: string[];
  totalCount: number;
  filteredCount: number;
  violationFilterEnabled?: boolean;
}) {
  const update = (partial: Partial<CreativeFilterState>) =>
    onChange({ ...filters, ...partial });

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Search */}
      <input
        type="text"
        placeholder="Search headline, text, angle…"
        className={cn(
          "h-8 w-56 rounded-md border border-border bg-surface px-2.5 text-xs text-content",
          "placeholder:text-content-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30",
        )}
        value={filters.search}
        onChange={(e) => update({ search: e.target.value })}
      />

      {/* Spec status */}
      <select
        className="h-8 rounded-md border border-border bg-surface px-2 text-xs text-content"
        value={filters.specStatus}
        onChange={(e) => update({ specStatus: e.target.value as CreativeFilterState["specStatus"] })}
      >
        <option value="all">All specs</option>
        <option value="ready">Spec ready</option>
        <option value="missing">No spec</option>
      </select>

      {/* Violations */}
      {violationFilterEnabled ? (
        <select
          className="h-8 rounded-md border border-border bg-surface px-2 text-xs text-content"
          value={filters.violationFilter}
          onChange={(e) =>
            update({ violationFilter: e.target.value as CreativeFilterState["violationFilter"] })
          }
        >
          <option value="all">All violations</option>
          <option value="has_violations">Has issues</option>
          <option value="clean">Clean</option>
        </select>
      ) : (
        <div className="flex h-8 items-center rounded-md border border-dashed border-border bg-surface px-2 text-xs text-content-muted">
          Policy filter unavailable
        </div>
      )}

      {/* Angle filter */}
      {angles.length > 1 ? (
        <select
          className="h-8 rounded-md border border-border bg-surface px-2 text-xs text-content"
          value={filters.angleFilter}
          onChange={(e) => update({ angleFilter: e.target.value })}
        >
          <option value="all">All angles</option>
          {angles.map((angle) => (
            <option key={angle} value={angle}>
              {angle}
            </option>
          ))}
        </select>
      ) : null}

      {/* Count */}
      <span className="text-xs text-content-muted">
        {filteredCount === totalCount
          ? `${totalCount} ads`
          : `${filteredCount} of ${totalCount} ads`}
      </span>
    </div>
  );
}
