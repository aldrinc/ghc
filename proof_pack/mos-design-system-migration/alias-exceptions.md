# Alias Exceptions

No borrowed-name aliases were added.

Kept semantic compatibility tokens:

- `surface-1` and `surface-2` remain as neutral surface levels because many product screens already use them and the names are not copied source or borrowed brand names.
- `shadow-1` and `shadow-2` remain as neutral elevation levels mapped to the new shadow scale for existing call sites.

Deletion condition:

- Remove `shadow-1` and `shadow-2` once all call sites use `shadow-sm`, `shadow-md`, `shadow-lg`, or component classes directly.
- Keep `surface-1` and `surface-2` as product semantics unless a future design-system spec replaces the surface-level model.
