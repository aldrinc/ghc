# Borrowed-Name Inventory

Target rule: production source should not expose borrowed design-system names. Source reference values may inform tokens, but copied API names should become MOS-owned or neutral names.

Pre-implementation findings from repo audit:

- `--manus-*` tokens existed in `mos/frontend/src/styles/theme.css`.
- `manus` Tailwind namespace entries existed in `mos/frontend/tailwind.config.ts`.
- A funnel template CSS reference used a copied name inside protected funnel output; that path was not redesigned in this pass.

Resolved in this implementation:

- Replaced `manus` token namespace with neutral token groups: `ink`, `blue`, `slate`, semantic surface/action/status tokens, spacing, radius, shadow, and motion scales.
- Removed `manus` Tailwind color and shadow namespaces.
- Added `mos/frontend/scripts/check-design-system-migration.mjs` to block `manus`, `--moz-`, `mozBlue`, and `moz-blue` in product source while allowing the real browser property `-moz-osx-font-smoothing`.

Current verification:

- `proof_pack/mos-design-system-migration/borrowed-name-scan.log`
- `proof_pack/mos-design-system-migration/logs/design-system-scan.log`
