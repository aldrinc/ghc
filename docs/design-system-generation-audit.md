# Design System Generation Audit Spec

## Purpose
Define a deterministic audit for newly generated design systems so we can reject inaccessible or visually unbalanced themes before they ship to funnel pages.

## Scope
- Funnel templates:
  - Sales PDP
  - Pre-sales listicle
- Surfaces:
  - Light surfaces (`--color-bg`, `--color-page-bg`, section surfaces)
  - Dark/saturated surfaces used in badges/cards/alerts
- Content types:
  - Body text
  - Muted/helper text
  - Heading text
  - Accent text
  - Interactive UI text (buttons, selected cards, chips, links)
  - Non-text UI boundaries (borders/icons/checkmarks)

## Inputs
- Design system tokens JSON (`dataTheme`, `cssVars`, `fontUrls`, `fontCss`, etc.)
- Funnel URLs for runtime verification:
  - `/sales`
  - `/pre-sales`
- Template CSS source files (for static checks)

## Outputs
- Structured audit report (JSON) with:
  - `check_id`
  - `status` (`pass`/`fail`)
  - `location` (token key, CSS selector, URL + selector)
  - `foreground`
  - `background`
  - `contrast_ratio`
  - `threshold`
  - `message`
- Markdown summary for human review

## Audit Steps

### 1. Token Schema + Required Keys
- Verify design system payload is a valid object.
- Verify required top-level keys exist and types are correct.
- Verify required `cssVars` keys exist and are non-empty string/number values.
- Fail if missing/invalid.

### 2. Token Reference Resolution
- Resolve `var(--...)` chains for every required token.
- Detect and fail on:
  - Circular references
  - Missing referenced tokens without fallback
  - Invalid CSS color formats where color is required

### 3. Light Surface Guardrail
- Evaluate luminance for core light-surface tokens:
  - `--color-page-bg`, `--color-bg`, `--hero-bg`, `--badge-strip-bg`, `--pitch-bg`, `--reviews-card-bg`, `--wall-card-bg`, `--pdp-surface-soft`, `--pdp-surface-muted`, `--pdp-swatch-bg`
- Blend alpha over white before luminance calculation.
- Fail if any surface is below the minimum luminance threshold.
- Note: dark accent bars/sections (for example marquee/footer treatments) are allowed as long as paired text tokens pass contrast checks.

### 4. Text Token Contrast Matrix
- Evaluate at least:
  - `--color-text` vs `--color-bg`
  - `--color-muted` vs `--color-bg`
  - `--color-text` vs `--color-page-bg`
  - `--color-muted` vs `--color-page-bg`
- Thresholds:
  - Normal text: >= 4.5:1
  - Long-form/body preferred target: >= 7.0:1 for `--color-text`
- Fail on any threshold breach.

### 5. Accent/Text Role Separation
- Enforce semantic separation:
  - `--color-text` must not resolve to same rendered color as `--color-brand`
  - `--color-muted` must not resolve to same rendered color as `--color-brand`
- Fail on role coupling.

### 6. Template CSS Static Usage Audit
- Parse template CSS for text-related properties:
  - `color`, `fill`, `stroke` where used for text/icons
- Flag selectors where accent tokens (`--color-brand`, `--pdp-brand-strong`) are used in general body/label/helper contexts.
- Allowlist intentional accent contexts (e.g., CTA emphasis, promotional badges).
- Fail if disallowed usage appears.

### 7. Runtime DOM Contrast Audit (Sales + Pre-sales)
- Load rendered funnel pages with applied design system tokens.
- Collect computed styles for visible text and UI targets:
  - Typography nodes
  - Buttons
  - Cards/options (default/selected)
  - Links
  - Alerts/banners
  - Icons/checkmarks
- Compute effective foreground/background and contrast ratio.
- Thresholds:
  - Text: WCAG AA (4.5:1 normal, 3.0:1 large)
  - UI component boundaries/icons: >= 3.0:1
- Fail with exact selector and values for each violation.

### 8. State Coverage Audit
- Verify key states:
  - Default
  - Hover/focus-visible
  - Selected/active
  - Disabled (if present)
- Fail if any state violates contrast thresholds.

### 9. Visual Balance Heuristic (Deterministic)
- Compute percentage of text nodes rendered with accent-like hue family.
- Compute percentage of screen area covered by accent-like foregrounds.
- Fail if either exceeds configured threshold outside allowlisted sections.
- Purpose: prevent “everything is pink” outcomes even when strict WCAG passes.

### 10. Report + Gate
- Aggregate all failures into one deterministic error report.
- If any failures exist:
  - Reject generation/persistence with explicit reasons
  - Include actionable remediation instructions per failed check
- If all pass:
  - Mark design system as validated

## Recommended Threshold Defaults
- `body_text_min_ratio`: `7.0`
- `normal_text_min_ratio`: `4.5`
- `large_text_min_ratio`: `3.0`
- `ui_boundary_min_ratio`: `3.0`
- `min_light_surface_luminance`: `0.65`
- `max_accent_text_share`: `0.35` (outside allowlist)

## Deterministic Pipeline Integration
- Run on:
  - Initial design system generation
  - Any design system token update
  - Optional nightly regressions against active funnels
- Block persistence/publication when status is `fail`.

## Current Automation Coverage
- Enforced now in backend validation:
  - Steps 1 through 5
  - Required contrast pairs from step 4 (expanded token pairs)
- Enforced now in runtime audit runner:
  - Step 7 text + border checks on `/sales` and `/pre-sales`
- Planned next (documented, not yet fully automated):
  - Step 6 static CSS role-usage parsing
  - Step 8 state-driven contrast sweeps
  - Step 9 accent density heuristic
  - Step 10 CI/persistence report artifact gating

## Local Runner
- Script: `mos/backend/scripts/run_design_system_audit.py`
- Example (funnel-based):
  - `cd mos/backend && python scripts/run_design_system_audit.py --public-id f30dc19f-b326-4e56-ac29-7d21a54556be`
- Example (explicit design system id):
  - `cd mos/backend && python scripts/run_design_system_audit.py --design-system-id ace54340-3713-456b-a774-e1a7b14c6da9 --public-id f30dc19f-b326-4e56-ac29-7d21a54556be`
- Outputs:
  - JSON report in `mos/backend/reports/`
  - Markdown summary in `mos/backend/reports/`

## Implementation Order
1. Keep strict token validation in backend services.
2. Add static CSS token-role audit.
3. Add runtime DOM contrast audit runner.
4. Merge both into single report schema + CI gate.
5. Persist report artifact per design system generation.
