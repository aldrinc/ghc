status: blocked_then_repaired

Volta audited the current implementation against the plan and found the real blockers:

- First-run components were imported but not rendered in onboarding.
- Workspace onboarding still showed explanatory cards before the actual flow.
- The wizard still used the old brand/product/audience/creative/review path.
- BrandDesignSystemPage did not expose first-run context, setup, review, or publish-state previews.
- Targeted onboarding tests were missing.

Main thread repaired these items and reran verification.
