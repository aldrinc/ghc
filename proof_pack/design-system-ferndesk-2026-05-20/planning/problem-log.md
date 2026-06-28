# Problem Log

## Active Problems
1. Current onboarding is a conventional multi-step form inside carded admin chrome.
   - Blocks: premium first-run experience.
   - Evidence: `WorkspaceOnboardingPage.tsx` wraps the wizard in explanatory cards; `OnboardingWizard.tsx` uses dense field groups, review cards, and a small step indicator.

2. Current design system is split between app tokens and funnel token JSON, with no first-run brand experience layer.
   - Blocks: making onboarding, setup status, review, and publish states feel cohesive.
   - Evidence: `theme.css` defines app tokens; `BrandDesignSystemPage.tsx` centers on a large funnel CSS-var template and JSON editing.

3. Current progress feedback is shallow.
   - Blocks: FernDesk-style "the system is doing work for you" perception.
   - Evidence: `JourneyIndicator` shows only short global status text like "Setting up..."; workflow detail pages expose logs, but onboarding does not present a focused setup theatre.

4. Current onboarding collects many manual fields up front.
   - Blocks: speed and perceived intelligence.
   - Evidence: required fields include brand story, product, target platforms, regions, proof assets, and voice notes before launch.

## Captured But Deferred
- Exact production data and API behavior must be verified during implementation. This plan does not invent source availability, job stages, or integration states.
