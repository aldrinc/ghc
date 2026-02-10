# UI Style Guide (Semantic Tokens)

This frontend is standardizing on a semantic token system backed by CSS variables.

## Source Of Truth

- Tokens live in `src/styles/theme.css` as CSS variables (e.g. `--background`, `--surface`, `--text`).
- Tailwind exposes semantic utilities in `tailwind.config.ts` (e.g. `bg-surface`, `text-content`, `border-border`).

## Dark Mode (Required)

Dark mode should be implemented by **switching token values**, not by sprinkling Tailwind `dark:*` variants in components.

- Preferred mechanism: set `data-theme="light" | "dark"` on `:root` (or the app root container).
- Define overrides in CSS (example shape):
  - `:root { ...light tokens... }`
  - `:root[data-theme="dark"] { ...dark overrides... }`

This keeps UI code purely semantic and avoids two styling systems.

## Rules (Hard Requirements)

### 1) Use Semantic Tokens, Not Palette Classes

Forbidden in app UI code:

- Neutral palettes like `slate-*`, `gray-*`, `zinc-*`, `neutral-*`, `stone-*`
- Status palettes like `amber-*`, `red-*`, `emerald-*`, `green-*`, `yellow-*`, `orange-*`, `rose-*`, `lime-*`
- Hard-coded surfaces like `bg-white`
- Tailwind dark variants like `dark:*`
- Hard-coded ring offsets like `ring-offset-white`

Use instead:

- Surfaces: `bg-background`, `bg-surface`, `bg-surface-2`, `bg-muted`
- Text: `text-content`, `text-content-muted`
- Borders: `border-border`, `border-divider`
- Interaction: `bg-hover`, `bg-active`, `text-accent`, `ring-accent/30`
- Status: `bg-warning/10 text-warning border-warning/30`, `bg-danger/10 text-danger border-danger/30`, `bg-success/10 text-success border-success/30`

### 2) Prefer Primitives Over Ad-Hoc Styling

Prefer these shared building blocks:

- `src/components/ui/*` (`Button`, `Input`, `Select`, `Tabs`, `Table`, etc.)
- `src/components/ui/callout.tsx` (`Callout` for warnings/errors/info banners)
- `src/styles/design-system.css` (`.ds-card` + modifiers)
- `src/components/layout/PageHeader.tsx`

Avoid re-inventing “filter bars”, “tab pills”, and “cards” per page.

## CI Enforcement (Incremental)

The repo includes an incremental check that blocks **new** forbidden palette usage and blocks **increasing** existing usage:

- Script: `scripts/check-semantic-ui.mjs`
- Baseline: `scripts/check-semantic-ui.baseline.json`

As violations are removed, the baseline will naturally become stricter.
