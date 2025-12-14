# ThemeAudit: Base UI docs-inspired theme (initial notes)

Source: quick static scrape of base-ui.com (curl) to seed token choices. Run a live devtools audit to finalize values and confirm portal/backdrop behaviors.

## Typography
- Sans: custom **Die Grotesk A/B** webfonts (woff2) with system fallbacks on the docs site; implementation stack set to `--font-sans: "Unica 77", system-ui, sans-serif` to approximate the condensed/modern look until a licensed source is added.
- Mono: not captured in static scrape (likely system mono); implementation stack set to `--font-mono: "SF Mono", "Menlo", "DejaVu Sans Mono", "Consolas", "Inconsolata", monospace`. TODO confirm actual docs mono in devtools (code/pre).
- Type scale from `.Text` utilities: 15/22 (size-1), 18/25 (size-2), 36/38 (size-3), 42/44 (size-4). Default line heights are tight (~1.5). Headings reuse the b weight (Die Grotesk B) for larger sizes.

## Colors & surfaces
- Root neutrals seen: `--gray-s1: white`, `--gray-s2: hsl(0deg 0% 97%)`, text `--gray-t2: hsl(0deg 0% 18%)`, `--border: hsl(0deg 0% 18%)`, `--selection: hsl(0deg 0% 92%)`. Dark-mode overrides exist but primary reference is light.
- Aesthetic: soft neutral background with white cards, low-contrast borders, and subdued text tones. Gradients on docs buttons/panels subtly lighten toward the top.

## Shape, elevation, spacing
- Radius: small radii (~8px outer, 7px inner) on buttons/popups; general rounded corners kept subtle.
- Shadows: layered, low-opacity shadows (e.g., `0 0.5px 1px .../12%`, `0 2px 4px -1px .../5%`, `0 8px 24px -4px .../5%`).
- Spacing tokens spotted: 4, 8, 12, 16, 20, 24, 32, 40, 48px; layout gaps favor tight-but-readable rhythm. Buttons use 32px height and 12px horizontal padding; menus use 32px row height.

## Overlay/interaction hooks
- Data attributes (e.g., `[data-panel-open]`) present for stateful styles; follow Base UI Dialog/Menu docs for open/close animations and nested dialog handling.
- TODO: confirm portal stacking/z-index defaults and backdrop animations via live inspection (ensure `isolation: isolate` on app root and `body { position: relative; }`).

## TODO for full audit
- Confirm mono font choice and code block styling.
- Capture root typography declarations (font-feature-settings/variations).
- Record actual z-index ladder for overlays and any motion tokens used for dialogs/menus/popovers.
