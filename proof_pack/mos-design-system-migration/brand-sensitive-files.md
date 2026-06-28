# Brand-Sensitive Files

Brand identity is excluded from this migration. This pass may change system styling around branded UI, but it must not redesign marks, wordmarks, customer brand output, or funnel identity helpers.

Protected paths reviewed:

- `mos/frontend/src/funnels/templates/shared/designSystemBrandLogo.ts`
- `mos/frontend/src/pages/auth/SignInPage.tsx`
- `mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx`
- `mos/frontend/src/app/AppShell.tsx`
- `mos/frontend/src/styles/theme.css`
- `mos/frontend/tailwind.config.ts`

Observed before implementation:

- `SignInPage.tsx`, `BrandDesignSystemPage.tsx`, and onboarding files already had local edits.
- Funnel template brand output was treated as protected and not refactored for this pass.

Implementation boundary:

- No MOS logo mark, wordmark text, funnel brand renderer, or customer brand asset path was intentionally changed by the design-system migration.
- Token and primitive changes are allowed where they affect generic product UI, controls, panels, typography, spacing, and semantic surfaces.
