# Problem Log

Primary problem:

- MOS has a new design-system reference, but the app still uses a partial older token/component system with copied vocabulary.

Observable evidence:

- `theme.css` still contains Manus-era palette and first-run-specific token groups.
- `tailwind.config.ts` still exposes a `manus` namespace.
- The source design-system file contains source/demo names that must be treated as values/examples, not permanent product API.
- `design-system.css` only covers a narrow set of shared classes.
- UI primitives encode sizes/radii/hover/focus behavior directly.
- Pages still hand-build panels, empty states, status badges, and action bars.

Scope risk:

- Brand identity code lives near app UI, so a broad migration can accidentally change logos, wordmarks, brand asset controls, or internal vocabulary that should remain product-owned/neutral.
