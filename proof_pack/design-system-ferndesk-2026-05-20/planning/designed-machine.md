# Designed Machine

## Visual Thesis
Quiet operator console with a warm editorial onboarding layer: crisp serif headlines, minimal black CTAs, soft neutral surfaces, useful context panels, and visible work progress.

## Design System First
1. Add app-level experience tokens:
   - near-white first-run canvas (`#FDFDFC`), pale chrome (`#ECECEC`), quiet app surface (`#F6F6F6`), warm callout (`#EFE6D5`), and black action (`#151411`), all sampled from the reference video.
   - typography roles: serif first-run display, sans body, sans labels, microcopy, mono/status.
   - action roles: full-width black primary CTA, quiet secondary action, skip, destructive.
   - progress roles: 2px top rail, setup checklist, status spinner, done state.
   - context roles: right-side setup preview, source checklist, generated-output preview, blocker panel, empty-state panel.
   - review roles: added/updated/deleted/missing/blocked labels.

2. Add reusable first-run components:
   - `FirstRunShell`
   - `ContextPreviewPanel`
   - `OnboardingProgressRail`
   - `ChoiceList`
   - `SetupChecklist`
   - `IntegrationPillGrid`
   - `AgentWorkLog`
   - `ReviewChangesPanel`
   - `PublishProgressDialog`

3. Upgrade design-system management:
   - show logo, palette, context panel, typography, CTA, input, chip, radius, shadow, onboarding shell, setup checklist, review-change, and publish-modal previews.
   - keep JSON editing as advanced mode.
   - add structured controls for core brand tokens so users do not need to reason through raw CSS vars first.

## Onboarding Second
1. Replace the current two-card page with a full-height split shell.
2. Convert big form steps into focused one-job screens.
3. Use domain, store, docs, assets, and integrations as source inputs where available.
4. Show real setup work through workflow/job status, not fake progress.
5. End in a review workspace where the user can inspect generated brand/product/research outputs before starting strategy work.

## Output
Onboarding feels like "Marketi is building my workspace" instead of "I am filling out Markti's setup form."
