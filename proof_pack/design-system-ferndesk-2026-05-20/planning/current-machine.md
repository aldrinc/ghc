# Current Machine

## Design System
- App tokens live in `mos/frontend/src/styles/theme.css`.
- Shared UI primitives live under `mos/frontend/src/components/ui/`.
- Design-system management lives in `mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx`.
- Funnel templates consume large CSS-var token objects through `DesignSystemProvider`.

## Onboarding
- Entry page: `mos/frontend/src/pages/workspaces/WorkspaceOnboardingPage.tsx`.
- Wizard: `mos/frontend/src/components/clients/OnboardingWizard.tsx`.
- Steps: brand, product, audience/channels, creative direction, review/launch.
- Completion: creates/selects workspace and product, starts onboarding, then navigates to `/workspaces/overview`.

## Feedback
- Global journey status is a small sidebar indicator in `AppShell.tsx`.
- Detailed workflow state is available through workflow detail surfaces, not a dedicated first-run setup theatre.

## Output
Functional onboarding, but low emotional signal and weak brand memory.
