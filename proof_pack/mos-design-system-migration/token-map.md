# Token Map

Core token layer installed in `mos/frontend/src/styles/theme.css` and exposed through `mos/frontend/tailwind.config.ts`.

Token groups:

- Typography: `--font-sans`, `--font-serif`, `--font-display`, `--font-mono`, `--text-2xs` through `--text-7xl`, line-height and tracking tokens.
- Color primitives: `--blue-*`, `--ink*`, `--slate-*`.
- Semantic surfaces: `--bg`, `--surface`, `--surface-1`, `--surface-2`, `--panel`, `--card`, `--border`, `--ring`, `--focus-outline`.
- Actions: `--primary`, `--secondary`, `--accent`, hover, active, and contrast tokens.
- Status: `--success`, `--warning`, `--danger`, `--info` plus matching background tokens.
- Layout scale: `--space-1` through `--space-13`.
- Radius scale: `--radius-xs` through `--radius-2xl`, plus `--radius-pill`, `--radius-panel`, `--radius-card`, `--radius-hero`, `--radius-prompt`.
- Elevation: `--shadow-xs` through `--shadow-xl`, plus blue and ink emphasis shadows.
- Motion: `--dur-fast`, `--dur-base`, `--dur-slow`, `--ease-out`, `--ease-in-out`.
- First-run/onboarding: `--first-run-*` remapped to the neutral product token layer.

Tailwind exposure:

- `colors.ink`, `colors.blue`, `colors.slate`, semantic `bg`, `surface`, `content`, `accent`, status, input, popover, card, sidebar, and chart colors.
- Token-backed `fontFamily`, `fontSize`, `lineHeight`, `letterSpacing`, `borderRadius`, `boxShadow`, and spacing entries.

Dark mode:

- Existing dark mode is preserved through semantic overrides, not through a separate brand identity change.
