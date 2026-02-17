# Design System Generation (Template Patch Mode)

## Goal
Generate brand-specific design system tokens reliably by starting from our base template and applying a small set of LLM-selected overrides (a "patch") instead of redesigning the entire theme from scratch.

This keeps templates visually stable (layout/geometry stays identical) while still letting brands feel distinct via accents and surface treatments (CTA/marquee/badges/section backgrounds).

## How It Works
Source of truth template:
- `mos/backend/app/templates/design_systems/base_tokens.json`

Default generation strategy:
- `generate_design_system_tokens(..., mode="template_patch")` (default)
- LLM returns a small JSON object with only overrides:
  - `cssVars`: array of `{ key, value }` pairs
  - optional `fontUrls` / `fontCss`
- Backend merges overrides into `base_tokens.json` to produce full tokens, then runs strict validation.

Full generation strategy (opt-in):
- `generate_design_system_tokens(..., mode="full")`
- LLM must output the full tokens object (higher variance; easier to violate constraints).

## Guardrails
Template patch mode enforces:
- Only keys that exist in the base template may be overridden.
- Layout/geometry CSS vars are locked and may never be overridden (`_LOCKED_LAYOUT_CSS_VAR_KEYS`).
- Patch size is capped to keep changes "small" and predictable.
- Final tokens are validated for:
  - required keys present
  - locked layout tokens unchanged
  - light-surface luminance floor
  - required text + non-text contrast pairs

## Practical Token Groups (What Usually Changes)
The patch prompt encourages the model to start with conversion and surface accents:
- CTA: `--color-cta`, `--color-cta-icon` (and if needed: `--color-cta-text`, `--pdp-cta-bg`, `--pdp-check-bg`)
- Marquee: `--marquee-bg`, `--marquee-text`
- Badges: `--badge-strip-bg`, `--badge-text-color`, `--badge-strip-border`
- Section backgrounds: `--hero-bg`, `--pitch-bg` (optional: `--color-page-bg`)

